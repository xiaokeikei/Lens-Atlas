package app.lensatlas.android

import org.json.JSONArray
import org.json.JSONObject

object LocalQueries {
    private fun values(f: JSONObject,key: String): List<String> = f.optJSONArray(key)?.let { a -> (0 until a.length()).map { a.getString(it) } } ?: emptyList()
    private val bounds = listOf(20.0,40.0,80.0,100.0,120.0,150.0,200.0,300.0,400.0,600.0,1000.0,Double.POSITIVE_INFINITY)
    fun filtered(items: List<MediaItem>,f: JSONObject): List<MediaItem> {
        val cameras=values(f,"cameras");val lenses=values(f,"lenses");val months=values(f,"months");val kinds=values(f,"kinds")
        val focals=values(f,"focals").map { it.toDouble() };val bins=values(f,"focal_bins").map { it.toInt() };val missing=values(f,"missing")
        require(bins.all { it in bounds.indices })
        val search=f.optString("search");val equivalent=f.optString("mode","equivalent")=="equivalent"
        return items.filter { i ->
            val focal=if(equivalent)i.equivalent else i.focal
            val fields=missingFields(i,equivalent)
            (cameras.isEmpty()||i.camera in cameras)&&(lenses.isEmpty()||i.lens in lenses)&&(months.isEmpty()||i.taken?.take(7) in months)&&(kinds.isEmpty()||i.kind in kinds)&&
            (focals.isEmpty()||focal in focals)&&(bins.isEmpty()||bins.any { b -> focal!=null&&focal>(if(b==0)0.0 else bounds[b-1])&&focal<=bounds[b] })&&
            missing.all { if(it=="any")fields.values.any { v->v } else fields[it]==true }&&(search.isBlank()||i.name.contains(search,true)||i.albumName.contains(search,true))
        }
    }
    private fun missingFields(i: MediaItem,equivalent: Boolean)=mapOf("camera" to(i.camera==null),"lens" to(i.lens==null),"focal" to((if(equivalent)i.equivalent else i.focal)==null),"time" to(i.taken==null))
    fun asset(i: MediaItem)=JSONObject().apply {
        put("id",i.uri);put("relpath",i.name);put("root_label",i.albumName);put("kind",i.kind);put("size",i.size);put("ext",i.name.substringAfterLast('.',""))
        put("camera",i.camera?:JSONObject.NULL);put("lens",i.lens?:JSONObject.NULL);put("taken_at",i.taken?:JSONObject.NULL);put("focal_native",i.focal?:JSONObject.NULL);put("focal_equiv",i.equivalent?:JSONObject.NULL)
        put("width",i.width);put("height",i.height);put("iso",i.iso?:JSONObject.NULL);put("aperture",i.aperture?:JSONObject.NULL);put("shutter",i.exposure?:JSONObject.NULL);put("duration",i.duration/1000.0);put("metadata_error",i.error?:JSONObject.NULL)
    }
    fun stats(items: List<MediaItem>,f: JSONObject): JSONObject {
        val rows=filtered(items,f);val equivalent=f.optString("mode","equivalent")=="equivalent"
        fun group(value:(MediaItem)->Any?):JSONArray=JSONArray().apply {
            rows.filter { value(it)!=null }.groupBy(value).entries.sortedWith(compareByDescending<Map.Entry<Any?,List<MediaItem>>> { it.value.size }.thenBy { it.key.toString() }).forEach { (key,items)->put(JSONObject().put("value",key).put("count",items.size).put("bytes",items.sumOf { it.size })) }
        }
        fun sorted(a:JSONArray,numeric:Boolean)=JSONArray().apply {
            (0 until a.length()).map { a.getJSONObject(it) }.sortedWith { a,b->if(numeric)a.getDouble("value").compareTo(b.getDouble("value")) else a.getString("value").compareTo(b.getString("value")) }.forEach { put(it) }
        }
        val missing=JSONObject()
        listOf("camera","lens","focal","time","any").forEach { key->val absent=rows.filter { val fields=missingFields(it,equivalent);if(key=="any")fields.values.any { v->v } else fields[key]==true };missing.put(key,JSONObject().put("count",absent.size).put("bytes",absent.sumOf { it.size })) }
        return JSONObject().put("summary",JSONObject().put("count",rows.size).put("bytes",rows.sumOf { it.size }).put("photos",rows.count { it.kind=="photo" }).put("videos",rows.count { it.kind=="video" }))
            .put("cameras",group { it.camera }).put("lenses",group { it.lens }).put("focals",sorted(group { if(equivalent)it.equivalent else it.focal },true)).put("months",sorted(group { it.taken?.take(7) },false)).put("missing",missing)
    }
}
