package app.lensatlas.android

import android.content.ContentUris
import android.content.Context
import android.content.ContentValues
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import android.net.Uri
import android.provider.MediaStore
import androidx.exifinterface.media.ExifInterface
import java.util.concurrent.atomic.AtomicBoolean

data class Album(val key: String, val label: String, val count: Int)
data class MediaItem(
    val uri: String, val name: String, val album: String, val albumName: String,
    val kind: String, val size: Long, val modified: Long, val width: Int, val height: Int,
    val taken: String?, val camera: String?, val lens: String?, val focal: Double?,
    val equivalent: Double?, val iso: String?, val aperture: String?, val exposure: String?,
    val duration: Long, val error: String?
)

/** All resolver operations are queries or read streams. SQLite writes target app-private storage only. */
class MediaLibrary(private val context: Context, dbName: String = "lens-index.db", private val testSources: List<Pair<Uri, String>>? = null) : SQLiteOpenHelper(context, dbName, null, 1) {
    override fun onCreate(db: SQLiteDatabase) {
        db.execSQL("CREATE TABLE media(uri TEXT PRIMARY KEY,name TEXT,album TEXT,albumName TEXT,kind TEXT,size INTEGER,modified INTEGER,width INTEGER,height INTEGER,taken TEXT,camera TEXT,lens TEXT,focal REAL,equivalent REAL,iso TEXT,aperture TEXT,exposure TEXT,duration INTEGER,error TEXT)")
        db.execSQL("CREATE TABLE scan_info(id INTEGER PRIMARY KEY CHECK(id=1),finished INTEGER,scope TEXT)")
    }
    override fun onUpgrade(db: SQLiteDatabase, old: Int, new: Int) = Unit
    private val resolver get() = context.contentResolver
    private val collections get() = testSources ?: listOf(MediaStore.Images.Media.getContentUri(MediaStore.VOLUME_EXTERNAL) to "photo", MediaStore.Video.Media.getContentUri(MediaStore.VOLUME_EXTERNAL) to "video").filter { (_, kind) ->
        fun granted(permission: String) = context.checkSelfPermission(permission) == android.content.pm.PackageManager.PERMISSION_GRANTED
        if (android.os.Build.VERSION.SDK_INT < 33) granted(android.Manifest.permission.READ_EXTERNAL_STORAGE)
        else granted(if (kind == "photo") android.Manifest.permission.READ_MEDIA_IMAGES else android.Manifest.permission.READ_MEDIA_VIDEO) ||
            (android.os.Build.VERSION.SDK_INT >= 34 && granted(android.Manifest.permission.READ_MEDIA_VISUAL_USER_SELECTED))
    }
    private val projection = arrayOf("_id", "_display_name", "bucket_id", "bucket_display_name", "relative_path", "_size", "date_modified", "width", "height", "datetaken")
    private fun albumKey(path: String?, bucket: String?) = path?.takeIf { it.isNotEmpty() } ?: "bucket:${bucket ?: "unknown"}"
    fun albums(): List<Album> {
        val result = linkedMapOf<String, Album>()
        collections.forEach { (collection, _) ->
            resolver.query(collection, arrayOf("bucket_id", "bucket_display_name", "relative_path"), null, null, null)?.use { c ->
                while (c.moveToNext()) {
                    val key = albumKey(c.getString(2), c.getString(0))
                    val old = result[key]
                    result[key] = Album(key, c.getString(2) ?: c.getString(1) ?: "未命名相册", (old?.count ?: 0) + 1)
                }
            }
        }
        return result.values.sortedBy { it.label }
    }
    fun lastScan(): String? = readableDatabase.rawQuery("SELECT finished,scope FROM scan_info WHERE id=1", null).use { c ->
        if (!c.moveToFirst()) null else java.text.DateFormat.getDateTimeInstance().format(java.util.Date(c.getLong(0))) + " · " + c.getString(1)
    }
    fun accessibleUris(): Set<String> {
        val result = HashSet<String>()
        collections.forEach { (collection, _) ->
            val cursor = resolver.query(collection, arrayOf("_id"), null, null, null) ?: throw IllegalStateException("无法读取授权图库，请重试")
            cursor.use { c -> while (c.moveToNext()) result += ContentUris.withAppendedId(collection, c.getLong(0)).toString() }
        }
        return result
    }
    fun items(): List<MediaItem> = readableDatabase.rawQuery("SELECT * FROM media ORDER BY taken DESC,name", null).use { c ->
        val result = ArrayList<MediaItem>()
        fun str(i: Int) = if (c.isNull(i)) null else c.getString(i)
        fun dbl(i: Int) = if (c.isNull(i)) null else c.getDouble(i)
        while (c.moveToNext()) result += MediaItem(c.getString(0), c.getString(1), c.getString(2), c.getString(3), c.getString(4), c.getLong(5), c.getLong(6), c.getInt(7), c.getInt(8), str(9), str(10), str(11), dbl(12), dbl(13), str(14), str(15), str(16), c.getLong(17), str(18))
        result
    }
    /** A cancelled/failed scan rolls back, preserving the previous completed index. */
    fun scan(selected: Set<String>?, cancelled: AtomicBoolean, scope: String, progress: (Int, Int) -> Unit) {
        check(collections.isNotEmpty()) { "相册授权已失效，上次索引保留" }
        val db = writableDatabase
        db.beginTransaction()
        try {
            db.delete("media", null, null)
            var processed = 0
            var failures = 0
            collections.forEach { (collection, kind) ->
                val cursor = resolver.query(collection, if (kind == "video") projection + "duration" else projection, null, null, "_id ASC") ?: throw IllegalStateException("无法读取授权图库，上次索引保留")
                cursor.use { c ->
                    while (c.moveToNext()) {
                        if (cancelled.get() || Thread.currentThread().isInterrupted) throw InterruptedException("扫描已取消，保留上次完成的索引")
                        val key = albumKey(c.getString(4), c.getString(2))
                        if (selected != null && key !in selected) continue
                        val uri = ContentUris.withAppendedId(collection, c.getLong(0))
                        var taken: String? = null
                        var camera: String? = null
                        var lens: String? = null
                        var focal: Double? = null
                        var equivalent: Double? = null
                        var iso: String? = null
                        var aperture: String? = null
                        var exposure: String? = null
                        var error: String? = null
                        if (kind == "photo") {
                            try {
                                resolver.openInputStream(uri)?.use { input ->
                                    val exif = ExifInterface(input)
                                    fun tag(name: String) = exif.getAttribute(name)?.trim()?.takeIf { it.isNotEmpty() }
                                    taken = tag(ExifInterface.TAG_DATETIME_ORIGINAL)?.replaceFirst(":", "-")?.replaceFirst(":", "-")
                                    camera = listOfNotNull(tag(ExifInterface.TAG_MAKE), tag(ExifInterface.TAG_MODEL)).distinct().joinToString(" ").ifEmpty { null }
                                    lens = tag(ExifInterface.TAG_LENS_MODEL)
                                    focal = exif.getAttributeDouble(ExifInterface.TAG_FOCAL_LENGTH, 0.0).takeIf { it > 0 }
                                    equivalent = exif.getAttributeDouble(ExifInterface.TAG_FOCAL_LENGTH_IN_35MM_FILM, 0.0).takeIf { it > 0 }
                                    iso = tag(ExifInterface.TAG_PHOTOGRAPHIC_SENSITIVITY)
                                    aperture = tag(ExifInterface.TAG_F_NUMBER)
                                    exposure = tag(ExifInterface.TAG_EXPOSURE_TIME)
                                } ?: throw IllegalStateException("无法打开素材")
                            } catch (e: Exception) { error = e.message ?: "元数据读取失败"; failures++ }
                        }
                        if (taken == null && !c.isNull(9) && c.getLong(9) > 0) taken = java.text.SimpleDateFormat("yyyy-MM-dd HH:mm:ss", java.util.Locale.ROOT).format(java.util.Date(c.getLong(9)))
                        val values = ContentValues().apply {
                            put("uri", uri.toString()); put("name", c.getString(1) ?: uri.lastPathSegment); put("album", key)
                            put("albumName", c.getString(4) ?: c.getString(3) ?: "未命名相册"); put("kind", kind)
                            put("size", c.getLong(5)); put("modified", c.getLong(6)); put("width", c.getInt(7)); put("height", c.getInt(8))
                            put("taken", taken); put("camera", camera); put("lens", lens); put("focal", focal); put("equivalent", equivalent)
                            put("iso", iso); put("aperture", aperture); put("exposure", exposure); put("duration", if (kind == "video") c.getLong(10) else 0L); put("error", error)
                        }
                        db.insertOrThrow("media", null, values)
                        processed++
                        if (processed % 20 == 0) progress(processed, failures)
                    }
                }
            }
            if (cancelled.get()) throw InterruptedException("扫描已取消，保留上次完成的索引")
            db.execSQL("INSERT OR REPLACE INTO scan_info VALUES(1,?,?)", arrayOf<Any>(System.currentTimeMillis(), scope))
            db.setTransactionSuccessful()
            progress(processed, failures)
        } finally { db.endTransaction() }
    }
    fun thumbnail(uri: String) = resolver.loadThumbnail(Uri.parse(uri), android.util.Size(320, 320), null)
}
