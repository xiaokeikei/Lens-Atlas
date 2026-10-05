package app.lensatlas.android

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import org.json.JSONObject
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

data class NasSession(val token:String,val expiresAt:Long)

/** Saves only authenticated session tokens, encrypted with an app-bound Android Keystore key. */
class SessionStore(context:Context,prefsName:String="remote-sessions",private val alias:String="lens-atlas-sessions-v1") {
    private val prefs=context.getSharedPreferences(prefsName,Context.MODE_PRIVATE)
    @Synchronized private fun key():SecretKey {
        val store=KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (store.getKey(alias,null) as? SecretKey)?.let { return it }
        return KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES,"AndroidKeyStore").apply {
            init(KeyGenParameterSpec.Builder(alias,KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT).setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).setKeySize(256).build())
        }.generateKey()
    }
    fun has(slot:Int)=prefs.contains("session$slot")
    fun forget(slot:Int){check(prefs.edit().remove("session$slot").commit()){ "无法清除保存的会话" }}
    fun save(slot:Int,url:String,session:NasSession) {
        require(slot in 0..2 && session.token.isNotBlank())
        val cipher=Cipher.getInstance("AES/GCM/NoPadding").apply { init(Cipher.ENCRYPT_MODE,key());updateAAD("$slot|$url".toByteArray(Charsets.UTF_8)) }
        val payload=JSONObject().put("token",session.token).put("expiresAt",session.expiresAt).toString()
        val encrypted=cipher.doFinal(payload.toByteArray(Charsets.UTF_8))
        val record=JSONObject().put("iv",Base64.encodeToString(cipher.iv,Base64.NO_WRAP)).put("cipher",Base64.encodeToString(encrypted,Base64.NO_WRAP))
        check(prefs.edit().putString("session$slot",record.toString()).commit()){ "无法安全保存会话" }
    }
    fun load(slot:Int,url:String):NasSession? {
        val stored=prefs.getString("session$slot",null)?:return null
        return try {
            val record=JSONObject(stored)
            val cipher=Cipher.getInstance("AES/GCM/NoPadding").apply {
                init(Cipher.DECRYPT_MODE,key(),GCMParameterSpec(128,Base64.decode(record.getString("iv"),Base64.NO_WRAP)))
                updateAAD("$slot|$url".toByteArray(Charsets.UTF_8))
            }
            val data=JSONObject(String(cipher.doFinal(Base64.decode(record.getString("cipher"),Base64.NO_WRAP)),Charsets.UTF_8))
            NasSession(data.getString("token"),data.getLong("expiresAt")).takeIf { it.expiresAt>System.currentTimeMillis()/1000 } ?: run { forget(slot);null }
        }catch(_:Exception){forget(slot);null}
    }
}
