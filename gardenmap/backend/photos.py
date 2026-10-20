"""Traitement des photos : date de prise de vue, rotation, versions réduites."""
import io
import uuid
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageOps

try:  # photos HEIC des iPhone, si la bibliothèque est disponible
    from pillow_heif import register_heif_opener

    register_heif_opener()
except ImportError:  # pragma: no cover
    pass

THUMB_SIZE = 400
EXIF_IFD = 0x8769
TAG_DATETIME_ORIGINAL = 36867
TAG_DATETIME = 306
SIZES = ("orig", "md", "th")


def exif_taken_at(img: Image.Image) -> str | None:
    """Date de prise de vue lue dans l'EXIF, en heure locale ISO (sans fuseau)."""
    try:
        exif = img.getexif()
    except Exception:
        return None
    raw = None
    try:
        raw = exif.get_ifd(EXIF_IFD).get(TAG_DATETIME_ORIGINAL)
    except Exception:
        pass
    raw = raw or exif.get(TAG_DATETIME)
    if not raw:
        return None
    try:
        return datetime.strptime(str(raw).strip()[:19], "%Y:%m:%d %H:%M:%S").isoformat()
    except ValueError:
        return None


def _save_resized(img: Image.Image, path: Path, max_side: int, quality: int) -> None:
    copy = img.copy()
    copy.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    if copy.mode not in ("RGB", "L"):
        copy = copy.convert("RGB")
    copy.save(path, "JPEG", quality=quality, optimize=True, progressive=True)


def process_upload(data: bytes, original_name: str, dest_dir: Path, max_side: int) -> dict:
    """Enregistre l'original et deux versions réduites. Lève ValueError si ce n'est pas une image."""
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception as exc:
        raise ValueError(f"Image illisible : {original_name}") from exc

    taken = exif_taken_at(img)
    img = ImageOps.exif_transpose(img)  # applique l'orientation EXIF

    dest_dir.mkdir(parents=True, exist_ok=True)
    base = uuid.uuid4().hex
    ext = (Path(original_name).suffix.lower().lstrip(".") or "jpg")[:5]
    (dest_dir / f"{base}_orig.{ext}").write_bytes(data)
    _save_resized(img, dest_dir / f"{base}_md.jpg", max_side, 85)
    _save_resized(img, dest_dir / f"{base}_th.jpg", THUMB_SIZE, 78)

    return {"filename": base, "ext": ext, "taken_at": taken, "width": img.width, "height": img.height}


def photo_path(photo_dir: Path, specimen_id: int, filename: str, ext: str, size: str) -> Path:
    if size == "orig":
        return photo_dir / str(specimen_id) / f"{filename}_orig.{ext}"
    return photo_dir / str(specimen_id) / f"{filename}_{size}.jpg"


def delete_files(photo_dir: Path, specimen_id: int, filename: str, ext: str) -> None:
    for size in SIZES:
        photo_path(photo_dir, specimen_id, filename, ext, size).unlink(missing_ok=True)
