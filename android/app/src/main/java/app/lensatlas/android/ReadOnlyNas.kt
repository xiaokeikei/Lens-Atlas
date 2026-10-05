package app.lensatlas.android

import org.json.JSONObject
import org.json.JSONArray
import org.json.JSONTokener
import java.net.HttpURLConnection
import java.net.URI
import java.net.URL

/** Original media stays read-only; scan commands may update only service-owned jobs/index/cache. */
object NasPolicy {
    fun allowed(method: String, path: String): Boolean = when (method) {
        "GET" -> path in setOf("/api/health", "/api/info", "/api/roots", "/api/jobs") || Regex("/api/assets/[0-9]+(?:/thumbnail)?").matches(path)
        "POST" -> path in setOf("/api/auth/login", "/api/auth/logout", "/api/stats", "/api/stats/focals", "/api/assets/query") || Regex("/api/roots/[1-9][0-9]*/scan").matches(path) || Regex("/api/jobs/[0-9a-fA-F-]{36}/(?:pause|resume|cancel)").matches(path)
        else -> false
    }
    fun validTarget(method: String, target: String): Boolean {
        val uri = try { URI(target) } catch (_: Exception) { return false }
        if (uri.scheme != null || uri.rawAuthority != null || uri.fragment != null || uri.rawPath != uri.path || !allowed(method, uri.path ?: "")) return false
        if (uri.rawQuery == null) return true
        return method == "GET" && Regex("/api/assets/[0-9]+/thumbnail").matches(uri.path) && Regex("expires=[0-9]+&sig=[0-9a-f]{64}").matches(uri.rawQuery)
    }
    fun base(value: String): String {
        val uri = URI(value.trim().trimEnd('/'))
        require(uri.scheme in setOf("http", "https") && !uri.host.isNullOrBlank() && uri.rawUserInfo == null && uri.query == null && uri.fragment == null) { "请输入有效 HTTP/HTTPS 服务地址，不要在地址中填写密码" }
        return uri.toASCIIString().trimEnd('/')
    }
}
class NasHttpException(val status:Int,message:String):IllegalStateException(message)
class ReadOnlyNas(address: String,session:NasSession?=null) {
    val base = NasPolicy.base(address)
    private var token = session?.token ?: ""
    var libraryKind="nas"
        private set
    private fun connection(method: String, path: String): HttpURLConnection {
        require(NasPolicy.validTarget(method, path)) { "只读客户端禁止此操作" }
        return (URL(base + path).openConnection() as HttpURLConnection).apply {
            requestMethod = method; connectTimeout = 12000; readTimeout = 25000
            instanceFollowRedirects = false
            if (token.isNotEmpty()) setRequestProperty("Authorization", "Bearer $token")
        }
    }
    private fun requestValue(path: String, body: JSONObject? = null): Any {
        val c = connection(if (body == null) "GET" else "POST", path)
        try {
            if (body != null) { c.doOutput = true; c.setRequestProperty("Content-Type", "application/json"); c.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) } }
            val code = c.responseCode
            if (code !in 200..299) {
                val message = c.errorStream?.bufferedReader()?.use { it.readText() }
                throw NasHttpException(code,if (code == 401) "登录已过期或密码错误，请重新连接" else "服务端请求失败 ($code)：${message ?: c.responseMessage}")
            }
            return JSONTokener(c.inputStream.bufferedReader().use { it.readText() }).nextValue()
        } finally { c.disconnect() }
    }
    fun request(path:String,body:JSONObject?=null)=requestValue(path,body) as JSONObject
    fun array(path:String)=requestValue(path) as JSONArray
    fun verifySession(){verifyHealth();request("/api/info")}
    private fun verifyHealth() {
        val health = request("/api/health")
        require(health.optInt("api_version") == 1 && health.optBoolean("ok")) { "NAS 接口版本不兼容" }
        require(!health.optBoolean("desktop")) { "电脑端请先开启“手机访问”，使用其显示的地址连接" }
        libraryKind=if(health.optString("library_kind")=="computer")"computer" else "nas"
        require(!health.optBoolean("setup_required")) { "请先在服务端完成管理员初始化" }
    }
    fun login(password:String,remember:Boolean=true):NasSession {
        verifyHealth()
        val result=request("/api/auth/login",JSONObject().put("password",password).put("remember",remember))
        token=result.getString("token")
        return NasSession(token,System.currentTimeMillis()/1000+result.getLong("expires_in"))
    }
    fun thumbnail(id: Long, signedPath: String? = null): android.graphics.Bitmap? {
        val path = signedPath ?: request("/api/assets/$id").getString("thumbnail_url")
        require(URI(path).path == "/api/assets/$id/thumbnail") { "缩略图地址与素材不匹配" }
        val c = connection("GET", path)
        try {
            require(c.responseCode == 200) { "预览暂不可用" }
            return c.inputStream.use { input ->
                val buffer = ByteArray(8192)
                val bytes = java.io.ByteArrayOutputStream()
                while (true) {
                    val read = input.read(buffer)
                    if (read < 0) break
                    require(bytes.size() + read <= 8 * 1024 * 1024) { "缩略图超过读取上限" }
                    bytes.write(buffer, 0, read)
                }
                val data = bytes.toByteArray()
                val bounds = android.graphics.BitmapFactory.Options().apply { inJustDecodeBounds = true }
                android.graphics.BitmapFactory.decodeByteArray(data, 0, data.size, bounds)
                require(bounds.outWidth > 0 && bounds.outHeight > 0) { "预览不是有效图片" }
                var sample = 1
                while (maxOf(bounds.outWidth, bounds.outHeight) / sample > 640) sample *= 2
                val options = android.graphics.BitmapFactory.Options().apply { inSampleSize = sample }
                android.graphics.BitmapFactory.decodeByteArray(data, 0, data.size, options)
            }
        } finally { c.disconnect() }
    }
}
