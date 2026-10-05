package app.lensatlas.android

import android.Manifest
import android.app.Activity
import android.app.AlertDialog
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.graphics.Bitmap
import android.util.Base64
import android.webkit.*
import android.widget.LinearLayout
import androidx.webkit.WebViewAssetLoader
import org.json.JSONArray
import org.json.JSONObject
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean

private class AppState(context: android.content.Context) {
    val library=MediaLibrary(context.applicationContext)
    val scanWorker=Executors.newSingleThreadExecutor()
    val io=Executors.newFixedThreadPool(3)
    val previews=Executors.newFixedThreadPool(2)
    val cancel=AtomicBoolean(false)
    val scanning=AtomicBoolean(false)
    val snapshotLock=Any()
    @Volatile var snapshot:List<MediaItem>?=null
    @Volatile var message="尚未扫描"
    @Volatile var lastScan:String?=null
    @Volatile var revision=0
    val remote=RemoteConnections(context.applicationContext)
}

/** Only bundled React assets can load; remote NAS pages never receive bridge access. */
class MainActivity:Activity() {
    private lateinit var state:AppState
    private lateinit var web:WebView
    private val origin="https://appassets.androidplatform.net"
    override fun onCreate(savedInstanceState:Bundle?) {
        super.onCreate(savedInstanceState)
        state=(lastNonConfigurationInstance as? AppState)?:AppState(applicationContext)
        if(WebView.getCurrentWebViewPackage()==null) {
            AlertDialog.Builder(this).setTitle("网页显示组件不可用").setMessage("镜迹使用与网页端相同的界面。当前系统没有可用的 Android System WebView，无法显示图库界面。请在提供该组件的安卓手机上使用本安装包。").setPositiveButton("关闭") { _,_->finish() }.setOnCancelListener { finish() }.show()
            return
        }
        val loader=WebViewAssetLoader.Builder().addPathHandler("/assets/",WebViewAssetLoader.AssetsPathHandler(this)).build()
        web=WebView(this)
        web.settings.apply { javaScriptEnabled=true;allowFileAccess=false;allowContentAccess=false;domStorageEnabled=false;mixedContentMode=WebSettings.MIXED_CONTENT_NEVER_ALLOW;setGeolocationEnabled(false) }
        web.webViewClient=object:WebViewClient() {
            override fun shouldOverrideUrlLoading(view:WebView,request:WebResourceRequest)=true
            override fun shouldInterceptRequest(view:WebView,request:WebResourceRequest):WebResourceResponse {
                val uri=request.url
                if(uri.scheme=="https"&&uri.host=="appassets.androidplatform.net"&&uri.path?.startsWith("/assets/")==true) {
                    loader.shouldInterceptRequest(uri)?.let { response->
                        response.responseHeaders=mapOf("Content-Security-Policy" to "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'none'; frame-src 'none'; object-src 'none'; base-uri 'none'")
                        return response
                    }
                }
                return WebResourceResponse("text/plain","UTF-8",403,"Blocked",emptyMap(),ByteArrayInputStream(ByteArray(0)))
            }
        }
        web.addJavascriptInterface(Bridge(),"LensAndroid")
        val outer=LinearLayout(this).apply {
            orientation=LinearLayout.VERTICAL
            @Suppress("DEPRECATION")
            setOnApplyWindowInsetsListener { view,insets->view.setPadding(0,insets.systemWindowInsetTop,0,insets.systemWindowInsetBottom);insets }
            addView(web,LinearLayout.LayoutParams(-1,-1))
        }
        setContentView(outer);outer.requestApplyInsets();web.loadUrl("$origin/assets/mobile.html")
        state.io.execute { state.lastScan=state.library.lastScan() }
        if(Build.VERSION.SDK_INT>=33)onBackInvokedDispatcher.registerOnBackInvokedCallback(android.window.OnBackInvokedDispatcher.PRIORITY_DEFAULT) { handleBack() }
    }
    @Deprecated("Retained scanner") override fun onRetainNonConfigurationInstance():Any=state
    override fun onResume() { super.onResume();if(::state.isInitialized){state.snapshot=null;state.revision++} }
    override fun onDestroy() {
        if(::web.isInitialized){web.removeJavascriptInterface("LensAndroid");web.destroy()}
        if(isFinishing){state.cancel.set(true);state.io.shutdownNow();state.previews.shutdownNow();state.scanWorker.execute { state.library.close() };state.scanWorker.shutdown()}
        super.onDestroy()
    }
    private fun granted(p:String)=checkSelfPermission(p)==PackageManager.PERMISSION_GRANTED
    private fun authorized()=if(Build.VERSION.SDK_INT<33)granted(Manifest.permission.READ_EXTERNAL_STORAGE) else granted(Manifest.permission.READ_MEDIA_IMAGES)||granted(Manifest.permission.READ_MEDIA_VIDEO)||(Build.VERSION.SDK_INT>=34&&granted(Manifest.permission.READ_MEDIA_VISUAL_USER_SELECTED))
    private fun scope()=if(Build.VERSION.SDK_INT<33||(granted(Manifest.permission.READ_MEDIA_IMAGES)&&granted(Manifest.permission.READ_MEDIA_VIDEO)))"全部已授权照片与视频" else "部分授权素材（不代表全部图库）"
    private fun authorize() {
        val permissions=if(Build.VERSION.SDK_INT>=34)arrayOf(Manifest.permission.READ_MEDIA_IMAGES,Manifest.permission.READ_MEDIA_VIDEO,Manifest.permission.READ_MEDIA_VISUAL_USER_SELECTED) else if(Build.VERSION.SDK_INT>=33)arrayOf(Manifest.permission.READ_MEDIA_IMAGES,Manifest.permission.READ_MEDIA_VIDEO) else arrayOf(Manifest.permission.READ_EXTERNAL_STORAGE)
        requestPermissions(permissions,10)
    }
    override fun onRequestPermissionsResult(requestCode:Int,permissions:Array<out String>,results:IntArray) {
        super.onRequestPermissionsResult(requestCode,permissions,results)
        if(requestCode==10){state.snapshot=null;state.revision++;state.message=if(authorized())"已授权：${scope()}" else "未获得相册读取权限"}
    }
    private fun snapshot():List<MediaItem> = synchronized(state.snapshotLock) {
        check(authorized()){ "请先授权读取相册" };check(!state.scanning.get()){ "请等待扫描完成后查看统计" }
        state.snapshot?:run { val accessible=state.library.accessibleUris();state.library.items().filter { it.uri in accessible }.also { state.snapshot=it } }
    }
    private fun scan(args:JSONObject):JSONObject {
        check(authorized()){ "请先授权读取相册" }
        val selected=if(args.isNull("selected"))null else args.getJSONArray("selected").let { a->(0 until a.length()).map { a.getString(it) }.toSet() }
        require(selected==null||selected.isNotEmpty()){ "请至少选择一个相册" }
        synchronized(state.snapshotLock){check(state.scanning.compareAndSet(false,true)){ "已有扫描正在进行" }}
        state.cancel.set(false);state.message="正在枚举已授权素材…"
        val model=state
        val scanScope=scope()+if(selected==null)" · 全部可访问相册" else " · 指定 ${selected.size} 个相册"
        model.scanWorker.execute {
            try { model.library.scan(selected,model.cancel,scanScope) { count,failures->model.message="已读取 $count 个素材 · 元数据异常 $failures 个" };synchronized(model.snapshotLock){model.snapshot=null};model.lastScan=model.library.lastScan();model.message="扫描完成：$scanScope" }
            catch(e:Exception){model.message=e.message?:"扫描失败，上次索引保留"}
            finally { model.scanning.set(false);model.revision++ }
        }
        return JSONObject().put("started",true)
    }
    private fun dispatch(action:String,args:JSONObject):Any {
        val source=args.optString("source","local");require(source=="local"||source=="nas")
        val nas=if(source=="nas")state.remote.client() else null;val filters=args.optJSONObject("filters")?:JSONObject()
        return when(action) {
            "status"->JSONObject().put("authorized",authorized()).put("scope",if(authorized())scope() else "未授权读取相册").put("scanning",state.scanning.get()).put("message",state.message).put("lastScan",state.lastScan?:JSONObject.NULL).put("revision",state.revision)
            "authorize"->{runOnUiThread { if(!isDestroyed)authorize() };JSONObject().put("requested",true)}
            "bootstrap"->state.remote.bootstrap()
            "restore"->state.remote.restore(args.getInt("slot"))
            "connections"->state.remote.records()
            "connect"->state.remote.connect(args.getInt("slot"),args.getString("name"),args.getString("url"),args.getString("password"),args.optBoolean("remember",true))
            "selectLocal"->{state.remote.selectLocal();JSONObject().put("ok",true)}
            "forget"->{state.remote.forget(args.getInt("slot"));JSONObject().put("ok",true)}
            "remoteRoots"->state.remote.client(args.getString("url")).array("/api/roots")
            "remoteJobs"->state.remote.client(args.getString("url")).array("/api/jobs")
            "remoteScan"->{
                val id=args.getInt("id");require(id>0)
                val client=state.remote.client(args.getString("url"))
                val job=client.request("/api/roots/$id/scan",JSONObject())
                if(job.optString("status")=="paused"){client.request("/api/jobs/${job.getString("id")}/resume",JSONObject());job.put("status","queued")}
                job
            }
            "remoteControl"->{
                val id=args.getString("id");val action=args.getString("action");require(action in setOf("pause","resume","cancel"))
                state.remote.client(args.getString("url")).request("/api/jobs/$id/$action",JSONObject())
            }
            "albums"->{check(authorized());check(!state.scanning.get());JSONArray().apply { state.library.albums().forEach { put(JSONObject().put("key",it.key).put("label",it.label).put("count",it.count)) } }}
            "scan"->scan(args)
            "cancel"->{state.cancel.set(true);JSONObject().put("requested",true)}
            "stats"->if(source=="nas"){checkNotNull(nas){ "请重新连接 NAS" };nas.request("/api/stats",filters)} else LocalQueries.stats(snapshot(),filters)
            "query"->{val limit=args.optInt("limit",24);val offset=args.optInt("offset",0);require(limit in 1..24&&offset>=0)
                if(source=="nas"){checkNotNull(nas){ "请重新连接 NAS" };nas.request("/api/assets/query",JSONObject().put("filters",filters).put("limit",limit).put("offset",offset).put("random",args.optBoolean("random")))}
                else {val rows=LocalQueries.filtered(snapshot(),filters);val page=if(args.optBoolean("random"))rows.shuffled().take(limit) else rows.drop(offset).take(limit);JSONObject().put("total",rows.size).put("items",JSONArray().apply { page.forEach { put(LocalQueries.asset(it)) } })}}
            "detail"->if(source=="nas"){checkNotNull(nas){ "请重新连接 NAS" };nas.request("/api/assets/${args.getLong("id")}")} else LocalQueries.asset(snapshot().firstOrNull { it.uri==args.getString("id") }?:error("素材当前不可访问，请重新扫描"))
            "thumbnail"->{val bitmap=if(source=="nas"){checkNotNull(nas){ "请重新连接 NAS" };nas.thumbnail(args.getLong("id"),args.optString("path").takeIf { it.isNotEmpty() })} else {val item=snapshot().firstOrNull { it.uri==args.getString("id") }?:error("素材当前不可访问");state.library.thumbnail(item.uri)};checkNotNull(bitmap){ "预览不可用" };try {val bytes=ByteArrayOutputStream();bitmap.compress(Bitmap.CompressFormat.JPEG,85,bytes);"data:image/jpeg;base64,"+Base64.encodeToString(bytes.toByteArray(),Base64.NO_WRAP)} finally {bitmap.recycle()}}
            else->error("只读客户端禁止此操作")
        }
    }
    inner class Bridge {
        @JavascriptInterface fun request(id:Int,action:String,payload:String) {
            if(id<1||payload.length>65536||isDestroyed)return
            val executor=if(action=="thumbnail")state.previews else state.io
            executor.execute {
                val response=try {JSONObject().put("result",dispatch(action,JSONObject(payload)))}catch(e:Exception){JSONObject().put("error",e.message?:"操作失败")}
                runOnUiThread {if(!isDestroyed&&web.url?.startsWith("$origin/assets/")==true)web.evaluateJavascript("window.__lensReply && window.__lensReply($id,${JSONObject.quote(response.toString())});",null)}
            }
        }
    }
    private fun handleBack(){if(!::web.isInitialized){finish();return};web.evaluateJavascript("window.__lensBack ? window.__lensBack() : false") { handled->if(handled!="true")finish() }}
    @Deprecated("Platform back") override fun onBackPressed(){handleBack()}
}
