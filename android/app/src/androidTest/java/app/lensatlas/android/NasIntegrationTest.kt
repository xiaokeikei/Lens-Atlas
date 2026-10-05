package app.lensatlas.android

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.json.JSONObject

@RunWith(AndroidJUnit4::class)
class NasIntegrationTest {
    @Test fun authenticateQueryFilterAndReadPreviewFromRealBackend() {
        val args = InstrumentationRegistry.getArguments()
        org.junit.Assume.assumeTrue("Local synthetic NAS server required", args.containsKey("nasUrl"))
        val client = ReadOnlyNas(args.getString("nasUrl")!!)
        client.login("AndroidFixture123!")
        val info = client.request("/api/info")
        assertEquals(1, info.getInt("api_version"))
        val stats = client.request("/api/stats", JSONObject())
        assertEquals(2, stats.getJSONObject("summary").getInt("count"))
        val filtered = JSONObject().put("search", "SYNTHETIC-1")
        assertEquals(1, client.request("/api/stats", filtered).getJSONObject("summary").getInt("count"))
        val results = client.request("/api/assets/query", JSONObject().put("filters", filtered).put("limit", 24).put("random", false))
        assertEquals(1, results.getInt("total"))
        val id = results.getJSONArray("items").getJSONObject(0).getLong("id")
        assertEquals("SYNTHETIC-1.jpg", client.request("/api/assets/$id").getString("relpath"))
        val image = client.thumbnail(id)
        assertNotNull(image); image?.recycle()
        assertThrows(IllegalArgumentException::class.java) { client.request("/api/roots", JSONObject().put("path", "/media")) }
    }
}
