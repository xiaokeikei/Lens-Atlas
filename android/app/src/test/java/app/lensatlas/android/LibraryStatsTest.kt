package app.lensatlas.android

import org.junit.Assert.*
import org.junit.Test

class LibraryStatsTest {
    private fun item(name: String, camera: String?, native: Double?, equivalent: Double?) = MediaItem("content://fixture/$name", name, "DCIM/", "DCIM/", "photo", 100, 0, 1, 1, "2026-10-01", camera, null, native, equivalent, null, null, null, 0, null)
    @Test fun combinedFiltersDescribeSamePopulation() {
        val items = listOf(item("旅行.jpg", "A", 24.0, 35.0), item("截图.jpg", "A", null, null), item("旅行2.jpg", "B", 24.0, 35.0))
        val filtered = items.filter { LibraryFilter(search = "旅行", camera = "A", month = "2026-10", focal = 35.0).matches(it) }
        assertEquals(listOf("旅行.jpg"), filtered.map { it.name })
        assertEquals(listOf("A" to 1), LibraryStats.groups(filtered) { it.camera })
    }
    @Test fun missingEquivalentDoesNotFallBackToNative() {
        val media = item("raw.dng", null, 24.0, null)
        assertFalse(LibraryFilter(focal = 24.0).matches(media))
        assertTrue(LibraryFilter(focal = 24.0, equivalent = false).matches(media))
        assertTrue(LibraryStats.groups(listOf(media)) { it.camera }.isEmpty())
    }
}
