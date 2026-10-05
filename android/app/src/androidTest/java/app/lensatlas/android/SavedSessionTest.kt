package app.lensatlas.android

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.json.JSONObject
import java.security.KeyStore

@RunWith(AndroidJUnit4::class)
class SavedSessionTest {
    private val context=InstrumentationRegistry.getInstrumentation().targetContext
    @Test fun tokenSurvivesNewStoreInstanceAndIsBoundToAddress() {
        val name="test-session-store";val alias="lens-test-session-store"
        context.getSharedPreferences(name,0).edit().clear().commit()
        try {
            val session=NasSession("SYNTHETIC-TOKEN-NOT-A-PASSWORD",System.currentTimeMillis()/1000+3600)
            SessionStore(context,name,alias).save(0,"https://fixture.test",session)
            val raw=context.getSharedPreferences(name,0).getString("session0","")!!
            assertFalse(raw.contains(session.token));assertFalse(raw.contains("PASSWORD"))
            assertEquals(session,SessionStore(context,name,alias).load(0,"https://fixture.test"))
            assertNull(SessionStore(context,name,alias).load(0,"https://other.test"))
            assertFalse(SessionStore(context,name,alias).has(0))
            SessionStore(context,name,alias).save(0,"https://fixture.test",NasSession("expired",1))
            assertNull(SessionStore(context,name,alias).load(0,"https://fixture.test"))
        }finally{context.getSharedPreferences(name,0).edit().clear().commit();KeyStore.getInstance("AndroidKeyStore").apply { load(null);deleteEntry(alias) }}
    }
    @Test fun coldConnectionRestoresWithoutPasswordAndCanStartServerScan() {
        val args=InstrumentationRegistry.getArguments();org.junit.Assume.assumeTrue(args.containsKey("nasUrl"))
        val name="test-remote-connections";val sessionName="test-remote-cipher";val alias="lens-test-remote-cipher"
        context.getSharedPreferences(name,0).edit().clear().commit();context.getSharedPreferences(sessionName,0).edit().clear().commit()
        try {
            val url=args.getString("nasUrl")!!
            val first=RemoteConnections(context,name,SessionStore(context,sessionName,alias))
            assertTrue(first.connect(0,"Synthetic NAS",url,"AndroidFixture123!",true).getBoolean("remembered"))
            val restarted=RemoteConnections(context,name,SessionStore(context,sessionName,alias))
            assertEquals(url,restarted.bootstrap().getJSONObject("active").getString("url"))
            assertTrue(restarted.restore(1).isNull("active"))
            assertEquals(0,restarted.bootstrap().getJSONObject("active").getInt("slot"))
            assertEquals(2,restarted.client().request("/api/stats",JSONObject()).getJSONObject("summary").getInt("count"))
            val root=restarted.client().array("/api/roots").getJSONObject(0).getInt("id")
            val job=restarted.client(url).request("/api/roots/$root/scan",JSONObject())
            assertTrue(job.getString("id").isNotBlank())
            var complete=false
            repeat(100){if(!complete){val jobs=restarted.client().array("/api/jobs");complete=(0 until jobs.length()).any { jobs.getJSONObject(it).getString("id")==job.getString("id")&&jobs.getJSONObject(it).getString("status")=="completed" };if(!complete)Thread.sleep(100)}}
            assertTrue("Server scan did not complete",complete)
            restarted.forget(0)
            assertFalse(restarted.records().getJSONObject(0).getBoolean("remembered"))
            assertTrue(RemoteConnections(context,name,SessionStore(context,sessionName,alias)).bootstrap().isNull("active"))
        }finally{context.getSharedPreferences(name,0).edit().clear().commit();context.getSharedPreferences(sessionName,0).edit().clear().commit();KeyStore.getInstance("AndroidKeyStore").apply { load(null);deleteEntry(alias) }}
    }
    @Test fun revokedServerSessionRequiresLoginAndPreservesAddress() {
        val args=InstrumentationRegistry.getArguments();org.junit.Assume.assumeTrue(args.containsKey("nasUrl"))
        val name="test-revoked-connections";val cipherName="test-revoked-cipher";val alias="lens-test-revoked-cipher"
        context.getSharedPreferences(name,0).edit().clear().commit();context.getSharedPreferences(cipherName,0).edit().clear().commit()
        try {
            val url=args.getString("nasUrl")!!
            val first=RemoteConnections(context,name,SessionStore(context,cipherName,alias));first.connect(0,"Synthetic",url,"AndroidFixture123!",true)
            first.client().request("/api/auth/logout",JSONObject())
            val restored=RemoteConnections(context,name,SessionStore(context,cipherName,alias)).bootstrap()
            assertTrue(restored.isNull("active"));assertEquals(url,restored.getJSONObject("login").getString("url"));assertFalse(SessionStore(context,cipherName,alias).has(0))
        }finally{context.getSharedPreferences(name,0).edit().clear().commit();context.getSharedPreferences(cipherName,0).edit().clear().commit();KeyStore.getInstance("AndroidKeyStore").apply { load(null);deleteEntry(alias) }}
    }
}
