from typing import Literal, Annotated
from pydantic import BaseModel, Field


class Filters(BaseModel):
    mode: Literal["equivalent", "native"] = "equivalent"
    cameras: list[str] = Field(default_factory=list, max_length=100)
    lenses: list[str] = Field(default_factory=list, max_length=100)
    focals: list[float] = Field(default_factory=list, max_length=100)
    focal_bins: list[Annotated[int, Field(ge=0, le=11)]] = Field(default_factory=list, max_length=12)
    months: list[str] = Field(default_factory=list, max_length=100)
    roots: list[int] = Field(default_factory=list, max_length=100)
    kinds: list[Literal["photo", "video"]] = Field(default_factory=list)
    missing: list[Literal["camera", "lens", "focal", "time", "any"]] = Field(default_factory=list)
    search: str = Field(default="", max_length=200)


def clause(filters):
    focal = "focal_equiv" if filters.mode == "equivalent" else "focal_native"
    sql = ["deleted=0", "kind IN ('photo','video')"]
    values = []
    if filters.focal_bins:
        ranges = []
        for index in filters.focal_bins:
            if index < 0 or index >= len(FOCAL_BOUNDS):
                raise ValueError('无效焦距区间')
            low = FOCAL_BOUNDS[index - 1] if index else 0
            high = FOCAL_BOUNDS[index]
            ranges.append(f'({focal}>?' + (f' AND {focal}<=?' if high is not None else '') + ')')
            values.append(low)
            if high is not None:
                values.append(high)
        sql.append('(' + ' OR '.join(ranges) + ')')
    for column, items in [("camera", filters.cameras), ("lens",filters.lenses),(focal,filters.focals),("substr(taken_at,1,7)",filters.months),("root_id",filters.roots),("kind",filters.kinds)]:
        if items:
            sql.append(column + " IN (" + ",".join("?" for _ in items) + ")")
            values.extend(items)
    missing = {"camera":"camera IS NULL", "lens":"lens IS NULL", "focal":focal+" IS NULL", "time":"taken_at IS NULL"}
    missing["any"] = "(" + " OR ".join(missing.values()) + ")"
    for field in filters.missing:
        sql.append(missing[field])
    if filters.search:
        sql.append("relpath LIKE ? ESCAPE '\\'")
        values.append("%" + filters.search.replace("\\","\\\\").replace("%","\\%").replace("_","\\_") + "%")
    return " AND ".join(sql), values, focal


FOCAL_BOUNDS = [20, 40, 80, 100, 120, 150, 200, 300, 400, 600, 1000, None]


def focal_distribution(db, filters):
    # Faceted context: retain every other filter, but remove the focal selection.
    context = filters.model_copy(update={'focals': [], 'focal_bins': []})
    where, args, focal = clause(context)
    rows = db.rows(f'SELECT {focal} value,COUNT(*) count,COALESCE(SUM(size),0) bytes '
                   f'FROM assets WHERE {where} AND {focal}>0 GROUP BY {focal} ORDER BY {focal}', args)
    bins = []
    for index, high in enumerate(FOCAL_BOUNDS):
        low = FOCAL_BOUNDS[index - 1] if index else 0
        selected = [r for r in rows if r['value'] > low and (high is None or r['value'] <= high)]
        bins.append({'value': index, 'lower': low, 'upper': high,
                     'label': f'≤{high}' if not index else f'>{low}' if high is None else f'{low}–{high}',
                     'count': sum(r['count'] for r in selected), 'bytes': sum(r['bytes'] for r in selected)})
    return {'bins': bins, 'values': rows}


def statistics(db, filters):
    # All groups share one read snapshot, including during concurrent scan writes.
    with db.connect() as connection:
        connection.execute('BEGIN')
        class Snapshot:
            def rows(self, sql, params=()):
                return [dict(row) for row in connection.execute(sql,params)]
            def one(self, sql, params=()):
                row=connection.execute(sql,params).fetchone()
                return dict(row) if row else None
        return _statistics(Snapshot(),filters)


def _statistics(db, filters):
    where, args, focal = clause(filters)
    result = {"mode":filters.mode}
    for name, expr in [("cameras","camera"),("lenses","lens"),("focals",focal),("months","substr(taken_at,1,7)")]:
        result[name] = db.rows(f"SELECT {expr} value,COUNT(*) count,COALESCE(SUM(size),0) bytes FROM assets WHERE {where} AND {expr} IS NOT NULL GROUP BY {expr} ORDER BY " + ("value" if name in {"focals","months"} else "count DESC,value"), args)
    result["summary"] = db.one(f"SELECT COUNT(*) count,COALESCE(SUM(size),0) bytes,SUM(kind='photo') photos,SUM(kind='video') videos FROM assets WHERE {where}",args)
    missing = [("camera", "camera IS NULL"),("lens","lens IS NULL"),("focal",focal+" IS NULL"),("time","taken_at IS NULL")]
    missing.append(("any", "(" + " OR ".join(exp for _,exp in missing) + ")"))
    result["missing"] = {name: db.one(f"SELECT COUNT(*) count,COALESCE(SUM(size),0) bytes FROM assets WHERE {where} AND {expr}",args) for name,expr in missing}
    result["states"] = db.rows(f"SELECT metadata_status,preview_status,COUNT(*) count FROM assets WHERE {where} GROUP BY metadata_status,preview_status",args)
    result["inventory"] = db.rows("SELECT kind,COUNT(*) count,COALESCE(SUM(size),0) bytes FROM assets WHERE deleted=0 GROUP BY kind")
    return result
