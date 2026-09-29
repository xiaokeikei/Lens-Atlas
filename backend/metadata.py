"""All external commands read sources only. This module also runs in bounded workers."""
from pathlib import Path
import io
import json
import math
import os
import re
import shutil
import subprocess
from PIL import Image, ImageOps, ExifTags
from .config import bundle_root

RAW = {"cr2", "cr3", "crw", "nef", "nrw", "arw", "srf", "sr2", "raf", "orf", "rw2", "raw", "pef", "ptx", "dng", "rwl", "3fr", "fff", "iiq", "kdc", "mos", "mrw", "x3f", "srw"}
PHOTO = RAW | {"jpg", "jpeg", "jpe", "png", "tif", "tiff", "heic", "heif", "avif", "webp", "bmp", "gif", "jxl"}
VIDEO = {"mp4", "mov", "m4v", "mkv", "avi", "mts", "m2ts", "mpg", "mpeg", "webm", "wmv", "3gp", "mxf"}
NONMEDIA = {"xmp", "txt", "json", "xml", "pdf", "doc", "docx", "ini", "db", "aae", "thm", "lrv", "csv", "md", "zip"}


def classify(path: Path):
    ext = path.suffix.lower().lstrip(".")
    return ("photo" if ext in PHOTO else "video" if ext in VIDEO else "nonmedia" if ext in NONMEDIA else "unknown"), ext


def tool(name):
    env = os.getenv("LENS_" + name.upper())
    if env and Path(env).is_file():
        return env
    suffix = ".exe" if os.name == "nt" else ""
    candidates = [bundle_root() / "vendor" / (name + suffix), bundle_root() / "vendor" / name / (name + suffix)]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return shutil.which(name)


def run(args, timeout=25, input=None):
    return subprocess.run(args, input=input, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout,
                          creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)


def run_exiftool(args, path: Path, timeout=25):
    # Windows Perl argv follows the system code page. UTF-8 argfile input bypasses
    # that conversion (ExifTool's documented WINDOWS UNICODE FILE NAMES approach).
    executable=tool('exiftool')
    path=path.resolve()
    if os.name=='nt':
        data=('\n'.join([*args,str(path)])+'\n').encode('utf-8')
        return run([executable,'-charset','filename=UTF8','-@','-'],timeout,input=data)
    return run([executable,'-charset','filename=UTF8',*args,str(path)],timeout)


def number(value):
    try:
        n = float(value)
        return n if math.isfinite(n) and n > 0 else None
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def normalize(tags):
    """Never infer crop factors from camera names or reuse native focal as equivalent."""
    def pick(*names):
        for name in names:
            for key, value in tags.items():
                if key == name or key.split(":")[-1] == name:
                    if isinstance(value,str):
                        value=value.strip()
                    if value not in (None, "", 0, "0"):
                        return value, key
        return None, None
    model, _ = pick("Model", "CameraModelName")
    make, _ = pick("Make")
    camera = str(model).strip() if model else None
    if camera and make and not camera.lower().startswith(str(make).lower()):
        camera = str(make).strip() + " " + camera
    lens = None
    raw_lens = None
    for name in ('LensModel','LensType','LensID','Lens'):
        for key,value in tags.items():
            if key.split(':')[-1] != name or value in (None,'',0,'0',-1,'-1'):
                continue
            value=str(value).strip()
            if not value:
                continue
            if re.fullmatch(r'(?:no[- ]?lens|unknown(?:\s*\([^)]*\))?|n/?a|none|undefined|null|not available|not set|-+)',value,re.IGNORECASE):
                continue
            if re.fullmatch(r'[\d\s./:+-]+',value):
                raw_lens=raw_lens or (key,value)
            elif lens is None:
                lens=value
    if lens is None and raw_lens:
        # Keep a vendor identifier distinct from a decoded model name.
        group=raw_lens[0].split(':')[0] if ':' in raw_lens[0] else 'Metadata'
        lens=f'{make or group} · Lens ID {raw_lens[1]}'
    native = number(pick("FocalLength")[0])
    equiv, source = pick("FocalLengthIn35mmFormat", "FocalLengthIn35mmFilm", "FocalLengthIn35mm")
    equiv = number(equiv)
    # ExifTool Composite:FocalLength35efl may infer undocumented crop factors. Do not use it.
    source = source if equiv else None
    date, time_source = pick("DateTimeOriginal", "SubSecDateTimeOriginal", "DateCreated", "CreationDate", "CreateDate")
    taken = None
    if date and re.match(r"^\d{4}[:\-]\d{2}[:\-]\d{2}[ T]\d{2}:\d{2}:\d{2}", str(date)):
        from datetime import datetime
        value = str(date)
        value = value[:10].replace(":", "-") + "T" + value[11:]
        offset, _ = pick("OffsetTimeOriginal")
        if offset and not re.search(r"(Z|[+-]\d\d:\d\d)$", value):
            value += str(offset)
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
            taken = value
        except ValueError:
            pass
    exposure, _ = pick("ExposureTime")
    codec, _ = pick("VideoCodec", "CompressorID")
    return dict(camera=camera, lens=str(lens).strip() if lens else None, focal_native=native,
                focal_equiv=equiv, focal_source=source, taken_at=taken, time_source=time_source if taken else None,
                aperture=number(pick("FNumber", "Aperture")[0]), shutter=str(exposure) if exposure else None,
                iso=number(pick("ISO", "ISOSpeedRatings", "PhotographicSensitivity")[0]), width=number(pick("ImageWidth", "ExifImageWidth")[0]),
                height=number(pick("ImageHeight", "ExifImageHeight")[0]),
                duration=number(pick("Duration")[0]), codec=str(codec) if codec else None)


def refresh_cached_metadata(db):
    """Upgrade normalized fields from saved tags; never reread or rewrite originals."""
    version=2
    if db.setting('normalizer_version',0)>=version:
        return 0
    last_id=0
    updated=0
    while True:
        rows=db.rows('SELECT id,metadata_json FROM assets WHERE id>? AND metadata_json IS NOT NULL ORDER BY id LIMIT 100',(last_id,))
        if not rows:
            break
        with db.connect() as connection:
            for row in rows:
                last_id=row['id']
                try:
                    tags=json.loads(row['metadata_json'])
                    if not isinstance(tags,dict):continue
                    values=normalize(tags)
                except (ValueError,TypeError):
                    continue
                connection.execute('UPDATE assets SET '+','.join(key+'=?' for key in values)+' WHERE id=?',(*values.values(),row['id']))
                updated+=1
    db.set_setting('normalizer_version',version)
    return updated


def extract(path: Path):
    # Preserve OS permission failures as their own state, before tool-specific parsing errors.
    with path.open('rb') as source:
        source.read(1)
    kind, ext = classify(path)
    tags, warnings, read_ok = {}, [], False
    executable = tool("exiftool")
    if executable:
        p = run_exiftool(['-j','-n','-G1'],path)
        try:
            tags = json.loads(p.stdout.decode("utf-8"))[0]
            errors = [str(v) for k, v in tags.items() if k.split(":")[-1] == "Error"]
            read_ok = p.returncode == 0 and not errors
            warnings.extend(errors)
            # A successful ExifTool invocation can identify text/PDF bytes under
            # a media suffix. That is not a successful media metadata read.
            detected_type = str(tags.get('File:FileType', '')).lower()
            detected_mime = str(tags.get('File:MIMEType', '')).lower()
            if detected_type in NONMEDIA or detected_mime.startswith('text/') or detected_mime in {'application/pdf', 'application/json', 'application/xml', 'application/zip'}:
                read_ok = False
                warnings.append('文件内容识别为非媒体类型（' + (detected_type or detected_mime) + '），与媒体扩展名不符')
        except (ValueError, IndexError):
            warnings.append("ExifTool 无法解析此文件")
    else:
        warnings.append("未安装 ExifTool；已尝试 Pillow 基础字段")
    if kind == "photo" and (not read_ok or not executable):
        try:
            with Image.open(path) as im:
                exif = im.getexif()
                combined = dict(exif)
                try:
                    combined.update(exif.get_ifd(34665))
                except (KeyError, TypeError):
                    pass
                for k, v in combined.items():
                    name = ExifTags.TAGS.get(k, str(k))
                    if isinstance(v, bytes):
                        continue
                    tags.setdefault("Pillow:" + name, float(v) if hasattr(v, "numerator") else v)
                tags["Pillow:ImageWidth"], tags["Pillow:ImageHeight"] = im.size
                read_ok = True
        except Exception as e:
            warnings.append(type(e).__name__ + ": 无法读取图片")
    if kind == "video" and tool("ffprobe"):
        p = run([tool("ffprobe"), "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)])
        if p.returncode == 0:
            probe = json.loads(p.stdout)
            stream = next((s for s in probe.get("streams", []) if s.get("codec_type") == "video"), {})
            fmt = probe.get("format", {})
            tags.update({"FFprobe:ImageWidth": stream.get("width"), "FFprobe:ImageHeight": stream.get("height"),
                         "FFprobe:Duration": fmt.get("duration"), "FFprobe:VideoCodec": stream.get("codec_name")})
            creation = fmt.get("tags", {}).get("creation_time") or stream.get("tags", {}).get("creation_time")
            if creation:
                tags["FFprobe:CreationDate"] = creation
            read_ok = True
        else:
            warnings.append("FFprobe 无法读取视频")
    data = normalize(tags)
    data.update(metadata_status="ok" if read_ok else "failed", metadata_error="; ".join(warnings) or None,
                playback_status="browser_candidate" if kind == "video" and ext in {"mp4", "m4v", "webm"} else "unsupported" if kind == "video" else "image_preview",
                metadata_json=json.dumps(tags, ensure_ascii=False, default=str))
    return data


def thumbnail(path: Path, target: Path):
    with path.open('rb') as source:
        source.read(1)
    kind, ext = classify(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if kind == "video":
        ffmpeg = tool("ffmpeg")
        if not ffmpeg:
            raise ValueError("缺少 FFmpeg，不能生成视频封面")
        p = run([ffmpeg, "-nostdin", "-v", "error", "-i", str(path), "-frames:v", "1", "-vf", "scale=1280:1280:force_original_aspect_ratio=decrease", "-y", str(target)])
        if p.returncode != 0 or not target.exists():
            raise ValueError("FFmpeg 无法解码视频封面")
        return
    im = None
    if ext in RAW and tool("exiftool"):
        for tag in ("PreviewImage", "JpgFromRaw", "OtherImage", "ThumbnailImage"):
            p = run_exiftool(['-b','-'+tag],path,timeout=12)
            if p.stdout:
                try:
                    im = Image.open(io.BytesIO(p.stdout))
                    im.load()
                    break
                except Exception:
                    im = None
    if im is None:
        try:
            im = Image.open(path)
        except Exception as e:
            raise ValueError("无可用内嵌预览或当前解码器不支持；元数据仍保留") from e
    with im:
        im = ImageOps.exif_transpose(im)
        im.thumbnail((1280, 1280))
        if im.mode != "RGB":
            im = im.convert("RGB")
        im.save(target, "JPEG", quality=84)
