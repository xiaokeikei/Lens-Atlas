package app.lensatlas.android

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject

class RemoteConnections(context:Context,prefsName:String="connections",private val sessions:SessionStore=SessionStore(context)) {
    private val prefs=context.getSharedPreferences(prefsName,Context.MODE_PRIVATE)
    @Volatile private var current:ReadOnlyNas?=null
    @Volatile private var currentSlot:Int?=null
    private var bootstrapped=false
    private fun connectionRecord(slot:Int)=JSONObject().put("slot",slot).put("name",prefs.getString("name$slot","连接 ${slot+1}")).put("url",prefs.getString("url$slot","")).put("kind",prefs.getString("kind$slot","nas")).put("remembered",sessions.has(slot))
    fun records()=JSONArray().apply { (0..2).forEach { put(connectionRecord(it)) } }
    @Synchronized fun connect(slot:Int,name:String,url:String,password:String,remember:Boolean):JSONObject {
        require(slot in 0..2)
        val client=ReadOnlyNas(url);val session=client.login(password,remember)
        var warning:String?=null
        try { if(remember)sessions.save(slot,client.base,session) else sessions.forget(slot) }catch(_:Exception){sessions.forget(slot);warning="本次已登录，但无法安全保存会话，关闭后需重新登录"}
        check(prefs.edit().putString("name$slot",name.trim().take(60).ifEmpty { "连接 ${slot+1}" }).putString("url$slot",client.base).putString("kind$slot",client.libraryKind).putInt("activeSlot",slot).commit())
        current=client;currentSlot=slot;bootstrapped=true
        return connectionRecord(slot).put("warning",warning?:JSONObject.NULL)
    }
    @Synchronized fun bootstrap():JSONObject {
        val slot=prefs.getInt("activeSlot",-1)
        val result=JSONObject().put("connections",records()).put("active",JSONObject.NULL).put("login",JSONObject.NULL)
        if(bootstrapped){if(currentSlot!=null&&current!=null)result.put("active",connectionRecord(currentSlot!!));return result}
        bootstrapped=true
        if(slot !in 0..2)return result
        val record=connectionRecord(slot);val url=record.getString("url")
        if(url.isBlank())return result
        val session=sessions.load(slot,url)
        if(session==null)return result.put("login",record).put("message","请登录一次以启用保持登录")
        val client=ReadOnlyNas(url,session)
        try { client.verifySession();prefs.edit().putString("kind$slot",client.libraryKind).apply() }
        catch(e:NasHttpException){if(e.status==401||e.status==403){sessions.forget(slot);return result.put("login",connectionRecord(slot)).put("message","登录已过期或被撤销，请重新登录")};result.put("message",e.message)}
        catch(e:Exception){result.put("message","暂时无法连接服务端，保存的会话仍保留；恢复网络后可刷新重试")}
        current=client;currentSlot=slot
        return result.put("active",connectionRecord(slot))
    }
    @Synchronized fun selectLocal(){prefs.edit().putInt("activeSlot",-1).apply();current=null;currentSlot=null;bootstrapped=true}
    @Synchronized fun restore(slot:Int):JSONObject {
        require(slot in 0..2)
        val previousClient=current;val previousSlot=currentSlot
        prefs.edit().putInt("activeSlot",slot).commit();current=null;currentSlot=null;bootstrapped=false
        val result=bootstrap()
        if(result.isNull("active")&&previousClient!=null&&previousSlot!=null){current=previousClient;currentSlot=previousSlot;prefs.edit().putInt("activeSlot",previousSlot).commit()}
        return result
    }
    fun client(expectedUrl:String?=null):ReadOnlyNas {
        val client=checkNotNull(current){ "请连接服务端" }
        require(expectedUrl==null||client.base==expectedUrl){ "图库已切换，请重新选择扫描目录" }
        return client
    }
    @Synchronized fun forget(slot:Int) {
        require(slot in 0..2)
        val url=connectionRecord(slot).getString("url")
        val saved=sessions.load(slot,url)
        try { if(saved!=null)ReadOnlyNas(url,saved).request("/api/auth/logout",JSONObject()) }catch(_:Exception){ }
        sessions.forget(slot)
        if(currentSlot==slot)selectLocal()
    }
}
