package app.lensatlas.android

import android.net.Uri
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.security.MessageDigest
import java.util.concurrent.atomic.AtomicBoolean
import org.json.JSONObject
import org.json.JSONArray

@RunWith(AndroidJUnit4::class)
class ReadOnlyScanTest {
    private val context = InstrumentationRegistry.getInstrumentation().targetContext
    private val fixture = Uri.parse("content://app.lensatlas.android.test.fixture/images")
    private fun digest(): String = context.contentResolver.openInputStream(Uri.withAppendedPath(fixture, "1"))!!.use { input ->
        MessageDigest.getInstance("SHA-256").digest(input.readBytes()).joinToString("") { "%02x".format(it) }
    }
    @Test fun scanSelectedAlbumAndPreserveOriginalBytes() {
        val name = "instrumentation-selected.db"
        context.deleteDatabase(name)
        MediaLibrary(context, name, listOf(fixture to "photo")).use { library ->
            val before = digest()
            assertEquals(2, library.albums().size)
            library.scan(setOf("Fixture-2/"), AtomicBoolean(false), "synthetic only") { _, _ -> }
            val items = library.items()
            assertEquals(1, items.size); assertEquals("Fixture-2/", items.single().album)
            assertEquals("SYNTHETIC Fixture Camera", items.single().camera)
            assertEquals(24.0, items.single().focal!!, 0.01)
            assertNull(items.single().equivalent)
            assertEquals("2026-10-05 12:00:00", items.single().taken)
            assertEquals(before, digest())
            val stats = LocalQueries.stats(items, JSONObject().put("mode", "native").put("cameras", JSONArray().put("SYNTHETIC Fixture Camera")).put("focal_bins", JSONArray().put(1)))
            assertEquals(1, stats.getJSONObject("summary").getInt("count"))
            assertEquals(1, stats.getJSONArray("focals").length())
            val equivalent = LocalQueries.stats(items, JSONObject())
            assertEquals(0, equivalent.getJSONArray("focals").length())
            assertEquals(1, equivalent.getJSONObject("missing").getJSONObject("focal").getInt("count"))
        }
        context.deleteDatabase(name)
    }
    @Test fun cancelledScanRollsBackIndexAndDoesNotWriteSource() {
        val name = "instrumentation-cancel.db"
        context.deleteDatabase(name)
        MediaLibrary(context, name, listOf(fixture to "photo")).use { library ->
            library.scan(null, AtomicBoolean(false), "completed") { _, _ -> }
            val beforeItems = library.items(); val beforeSource = digest(); val beforeScan = library.lastScan()
            try { library.scan(null, AtomicBoolean(true), "cancelled") { _, _ -> }; fail("Expected cancellation") }
            catch (_: InterruptedException) { }
            assertEquals(beforeItems, library.items()); assertEquals(beforeScan, library.lastScan()); assertEquals(beforeSource, digest())
        }
        context.deleteDatabase(name)
    }
}
