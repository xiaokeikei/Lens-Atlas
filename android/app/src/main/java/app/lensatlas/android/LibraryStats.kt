package app.lensatlas.android

data class LibraryFilter(val search: String = "", val kind: String? = null, val camera: String? = null, val lens: String? = null, val month: String? = null, val focal: Double? = null, val equivalent: Boolean = true) {
    fun matches(item: MediaItem): Boolean =
        (search.isBlank() || item.name.contains(search, true) || item.albumName.contains(search, true)) &&
        (kind == null || item.kind == kind) && (camera == null || item.camera == camera) &&
        (lens == null || item.lens == lens) && (month == null || item.taken?.take(7) == month) &&
        (focal == null || (if (equivalent) item.equivalent else item.focal) == focal)
}
object LibraryStats {
    fun groups(items: List<MediaItem>, value: (MediaItem) -> String?): List<Pair<String, Int>> =
        items.mapNotNull(value).groupingBy { it }.eachCount().entries.sortedWith(compareByDescending<Map.Entry<String, Int>> { it.value }.thenBy { it.key }).map { it.key to it.value }
}
