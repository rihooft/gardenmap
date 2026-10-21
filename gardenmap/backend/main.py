"""API GardenMap (FastAPI). Servie derrière l'ingress de Home Assistant."""
import base64
import io
import json
import os
import sqlite3
import zipfile
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

import httpx
from fastapi import Body, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image

from . import ai, db, ha, photos
from . import geo
from .fields import FIELD_BY_KEY, SPECIES_FIELDS, catalog, clean_value

PLAN_MAX_SIDE = 6000
STATIC_DIR = Path(os.environ.get("GARDENMAP_STATIC", Path(__file__).parent.parent / "static"))
OPTIONS_FILE = db.DATA_DIR / "options.json"
ALLOWED_CLIENTS = {"172.30.32.2", "127.0.0.1", "::1", "testclient"}

@asynccontextmanager
async def lifespan(_app):
    db.init_db()
    yield


app = FastAPI(title="GardenMap", docs_url="/api/docs", openapi_url="/api/openapi.json", lifespan=lifespan)


@app.middleware("http")
async def only_ingress(request: Request, call_next):
    """L'add-on n'expose aucun port : seul le proxy d'ingress (172.30.32.2) doit l'appeler."""
    if os.environ.get("GARDENMAP_ALLOW_ALL") != "1":
        host = request.client.host if request.client else ""
        if host not in ALLOWED_CLIENTS:
            return JSONResponse({"detail": "Accès réservé à l'ingress Home Assistant"}, status_code=403)
    return await call_next(request)


def options() -> dict:
    try:
        return json.loads(OPTIONS_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def not_found(what: str):
    raise HTTPException(404, f"{what} introuvable")


# ---------------------------------------------------------------------------
# Catalogue et état général
# ---------------------------------------------------------------------------
@app.get("/api/meta")
def meta():
    opts = options()
    return {
        **catalog(),
        "zone_kinds": geo.ZONE_KINDS,
        "garden": db.get_setting("garden"),
        "custom_source": db.get_setting("custom_source"),
        "ai_enabled": opts.get("ai_provider", "none") != "none",
        "ha_api": bool(os.environ.get("SUPERVISOR_TOKEN")),
        "tracker_entity": db.get_setting("tracker_entity"),
    }


@app.put("/api/settings/custom-source")
def set_custom_source(payload: dict = Body(...)):
    """Fond de carte supplémentaire (tuiles XYZ ou WMTS en EPSG:3857), choisi par l'utilisateur."""
    url = str(payload.get("url") or "").strip()
    if not url:
        db.set_setting("custom_source", None)
        return {"custom_source": None}
    if not url.startswith("https://"):
        raise HTTPException(400, "L'adresse doit commencer par https:// (sinon le navigateur la bloque).")
    missing = [p for p in ("{z}", "{x}", "{y}") if p not in url]
    if missing:
        raise HTTPException(400, f"Il manque {', '.join(missing)} dans l'adresse des tuiles.")
    try:
        native = int(payload.get("native") or 19)
    except (TypeError, ValueError):
        raise HTTPException(400, "Zoom maximal invalide")
    src = {
        "label": (str(payload.get("label") or "").strip() or "Source personnalisée")[:40],
        "url": url[:1000],
        "native": max(10, min(23, native)),
        "attribution": str(payload.get("attribution") or "").strip()[:200],
    }
    db.set_setting("custom_source", src)
    return {"custom_source": src}


@app.put("/api/settings/tracker")
def set_tracker(payload: dict = Body(...)):
    db.set_setting("tracker_entity", payload.get("entity_id") or None)
    return {"tracker_entity": payload.get("entity_id") or None}


# ---------------------------------------------------------------------------
# Emplacement du jardin
# ---------------------------------------------------------------------------
GEOCODER = os.environ.get("GARDENMAP_GEOCODER", "https://data.geopf.fr/geocodage/search")


@app.get("/api/garden")
def get_garden():
    return db.get_setting("garden")


@app.put("/api/garden")
def set_garden(payload: dict = Body(...)):
    try:
        lat, lon = float(payload["lat"]), float(payload["lon"])
        zoom = float(payload.get("zoom") or 19)
    except (KeyError, TypeError, ValueError):
        raise HTTPException(400, "Position du jardin invalide (lat, lon)")
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise HTTPException(400, "Coordonnées hors limites")
    garden = {"lat": lat, "lon": lon, "zoom": max(14.0, min(22.0, zoom)), "label": str(payload.get("label") or "")[:200]}
    db.set_setting("garden", garden)
    return garden


@app.get("/api/geocode")
async def geocode(q: str):
    """Recherche d'adresse via le géocodeur de l'IGN (Géoplateforme)."""
    q = q.strip()
    if len(q) < 3:
        return []
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(GEOCODER, params={"q": q, "limit": 6})
        r.raise_for_status()
        feats = r.json().get("features", [])
    except Exception as exc:
        raise HTTPException(502, f"Recherche d'adresse indisponible : {exc}")
    out = []
    for f in feats:
        try:
            lon, lat = f["geometry"]["coordinates"][:2]
        except (KeyError, TypeError, ValueError):
            continue
        p = f.get("properties", {})
        out.append({"label": p.get("label") or p.get("name") or "", "lat": lat, "lon": lon, "type": p.get("type")})
    return out


# ---------------------------------------------------------------------------
# Zones du jardin (aplats)
# ---------------------------------------------------------------------------
def _zone(conn, zone_id: int) -> dict:
    row = db.row_to_dict(conn.execute("SELECT * FROM zones WHERE id = ?", (zone_id,)).fetchone())
    if not row:
        not_found("Zone")
    row.update(geo.measure(row["geometry"]))
    return row


def _zone_values(payload: dict, existing: dict | None) -> dict:
    kind = payload.get("kind", (existing or {}).get("kind"))
    meta = geo.KIND_BY_KEY.get(kind)
    if not meta:
        raise HTTPException(400, "Type de zone inconnu")
    geometry = payload.get("geometry", (existing or {}).get("geometry"))
    try:
        geometry = geo.clean_geometry(geometry, meta["geom"])
    except geo.GeometryError as exc:
        raise HTTPException(400, str(exc))
    vals = {k: payload.get(k, (existing or {}).get(k)) for k in ("name", "notes")}
    vals = {k: (str(v).strip()[:2000] or None) if v is not None else None for k, v in vals.items()}
    return {"kind": kind, "geometry": json.dumps(geometry), **vals}


@app.get("/api/zones")
def list_zones():
    with db.tx() as c:
        rows = [db.row_to_dict(r) for r in c.execute("SELECT * FROM zones ORDER BY id")]
    for r in rows:
        r.update(geo.measure(r["geometry"]))
    return rows


@app.post("/api/zones", status_code=201)
def create_zone(payload: dict = Body(...)):
    vals = _zone_values(payload, None)
    now = db.now_iso()
    with db.tx() as c:
        cur = c.execute(
            "INSERT INTO zones(kind, name, geometry, notes, created_at, updated_at) VALUES (:kind, :name, :geometry, :notes, :now, :now)",
            {**vals, "now": now},
        )
        return _zone(c, cur.lastrowid)


@app.put("/api/zones/{zone_id}")
def update_zone(zone_id: int, payload: dict = Body(...)):
    with db.tx() as c:
        existing = _zone(c, zone_id)
        if "kind" in payload and geo.KIND_BY_KEY.get(payload["kind"], {}).get("geom") != geo.KIND_BY_KEY[existing["kind"]]["geom"] and "geometry" not in payload:
            raise HTTPException(400, "Une surface ne peut pas devenir une ligne (et inversement).")
        vals = _zone_values(payload, existing)
        c.execute(
            "UPDATE zones SET kind=:kind, name=:name, geometry=:geometry, notes=:notes, updated_at=:now WHERE id=:id",
            {**vals, "now": db.now_iso(), "id": zone_id},
        )
        return _zone(c, zone_id)


@app.delete("/api/zones/{zone_id}", status_code=204)
def delete_zone(zone_id: int):
    with db.tx() as c:
        c.execute("DELETE FROM zones WHERE id = ?", (zone_id,))


# ---------------------------------------------------------------------------
# Espèces
# ---------------------------------------------------------------------------
SPECIES_TOP = ("common_name", "botanical_name", "cultivar", "family", "category")


def clean_attrs(attrs: dict) -> dict:
    out = {}
    for f in SPECIES_FIELDS:
        if f["key"] in attrs:
            v = clean_value(f, attrs[f["key"]])
            if v is not None:
                out[f["key"]] = v
    return out


def get_species_row(conn, species_id: int) -> dict:
    row = db.row_to_dict(conn.execute("SELECT * FROM species WHERE id = ?", (species_id,)).fetchone())
    if not row:
        not_found("Espèce")
    row["specimen_count"] = conn.execute(
        "SELECT COUNT(*) FROM specimens WHERE species_id = ?", (species_id,)
    ).fetchone()[0]
    return row


@app.get("/api/species")
def list_species():
    with db.tx() as c:
        rows = c.execute(
            "SELECT s.*, (SELECT COUNT(*) FROM specimens p WHERE p.species_id = s.id) AS specimen_count "
            "FROM species s ORDER BY s.common_name COLLATE NOCASE"
        ).fetchall()
    return [db.row_to_dict(r) for r in rows]


@app.get("/api/species/{species_id}")
def get_species(species_id: int):
    with db.tx() as c:
        return get_species_row(c, species_id)


def _species_values(payload: dict, existing: dict | None) -> dict:
    vals = {k: (payload.get(k) if k in payload else (existing or {}).get(k)) for k in SPECIES_TOP}
    vals = {k: (str(v).strip() or None) if v is not None else None for k, v in vals.items()}
    if not vals["common_name"]:
        raise HTTPException(400, "Le nom commun est obligatoire.")
    attrs = dict((existing or {}).get("attrs", {}))
    if "attrs" in payload:
        attrs = clean_attrs(payload["attrs"] or {})
    meta = dict((existing or {}).get("attr_meta", {}))
    if "attr_meta" in payload:
        meta = {k: v for k, v in (payload["attr_meta"] or {}).items() if k in FIELD_BY_KEY and isinstance(v, dict)}
    # un champ vidé n'a plus de provenance
    meta = {k: v for k, v in meta.items() if k in attrs or vals.get(k)}
    return {**vals, "attrs": json.dumps(attrs, ensure_ascii=False), "attr_meta": json.dumps(meta, ensure_ascii=False)}


@app.post("/api/species", status_code=201)
def create_species(payload: dict = Body(...)):
    vals = _species_values(payload, None)
    now = db.now_iso()
    with db.tx() as c:
        cur = c.execute(
            "INSERT INTO species(common_name, botanical_name, cultivar, family, category, attrs, attr_meta, created_at, updated_at) "
            "VALUES (:common_name, :botanical_name, :cultivar, :family, :category, :attrs, :attr_meta, :now, :now)",
            {**vals, "now": now},
        )
        return get_species_row(c, cur.lastrowid)


@app.put("/api/species/{species_id}")
def update_species(species_id: int, payload: dict = Body(...)):
    with db.tx() as c:
        existing = get_species_row(c, species_id)
        vals = _species_values(payload, existing)
        c.execute(
            "UPDATE species SET common_name=:common_name, botanical_name=:botanical_name, cultivar=:cultivar, "
            "family=:family, category=:category, attrs=:attrs, attr_meta=:attr_meta, updated_at=:now WHERE id=:id",
            {**vals, "now": db.now_iso(), "id": species_id},
        )
        return get_species_row(c, species_id)


@app.delete("/api/species/{species_id}", status_code=204)
def delete_species(species_id: int):
    with db.tx() as c:
        sp = get_species_row(c, species_id)
        if sp["specimen_count"]:
            raise HTTPException(409, "Cette espèce est utilisée par des spécimens.")
        c.execute("DELETE FROM species WHERE id = ?", (species_id,))


@app.post("/api/species/{species_id}/enrich")
async def enrich_species(species_id: int):
    with db.tx() as c:
        sp = get_species_row(c, species_id)
    try:
        result = await ai.enrich(options(), sp)
    except ai.AIError as exc:
        raise HTTPException(502, str(exc))
    except Exception as exc:  # réseau, délai…
        raise HTTPException(502, f"Appel à l'IA impossible : {exc}")
    # On ne propose pas d'écraser une valeur validée ou saisie à la main.
    locked = {k for k, m in sp["attr_meta"].items() if not m.get("pending")}
    locked |= {k for k in sp["attrs"] if k not in sp["attr_meta"]}
    locked |= {k for k in ("botanical_name", "family", "category") if sp.get(k) and k not in sp["attr_meta"]}
    result["proposals"] = {k: v for k, v in result["proposals"].items() if k not in locked}
    result["generated_at"] = db.now_iso()
    return result


# ---------------------------------------------------------------------------
# Spécimens
# ---------------------------------------------------------------------------
SPECIMEN_FIELDS = (
    "species_id", "nickname", "lat", "lon", "gps_accuracy", "position_source",
    "planted_on", "age_years", "age_estimated_on", "origin", "status", "exposure", "soil",
    "irrigation_zone", "notes",
)
NUMERIC = {"lat", "lon", "gps_accuracy", "age_years"}

SPECIMEN_LIST_SQL = """
SELECT p.*, s.common_name, s.botanical_name, s.cultivar, s.category,
       (SELECT ph.id FROM photos ph WHERE ph.specimen_id = p.id ORDER BY ph.taken_at DESC, ph.id DESC LIMIT 1) AS cover_photo_id,
       (SELECT COUNT(*) FROM photos ph WHERE ph.specimen_id = p.id) AS photo_count,
       (SELECT COUNT(*) FROM events e WHERE e.specimen_id = p.id AND e.kind = 'observation'
            AND COALESCE(e.status, 'ouvert') = 'ouvert') AS open_issues
FROM specimens p LEFT JOIN species s ON s.id = p.species_id
"""


def _specimen_values(payload: dict, existing: dict | None) -> dict:
    vals = {}
    for k in SPECIMEN_FIELDS:
        v = payload.get(k) if k in payload else (existing or {}).get(k)
        if v == "":
            v = None
        if k in NUMERIC and v is not None:
            try:
                v = float(v)
            except (TypeError, ValueError):
                raise HTTPException(400, f"Valeur numérique invalide pour {k}")
        vals[k] = v
    vals["status"] = vals["status"] or "en_place"
    tags = payload.get("tags") if "tags" in payload else (existing or {}).get("tags", [])
    vals["tags"] = json.dumps([str(t).strip() for t in (tags or []) if str(t).strip()], ensure_ascii=False)
    if (vals["lat"] is None) != (vals["lon"] is None):
        raise HTTPException(400, "Latitude et longitude vont ensemble.")
    if vals["lat"] is not None and not (-90 <= vals["lat"] <= 90 and -180 <= vals["lon"] <= 180):
        raise HTTPException(400, "Coordonnées hors limites")
    return vals


def get_specimen_full(conn, specimen_id: int) -> dict:
    row = db.row_to_dict(conn.execute(SPECIMEN_LIST_SQL + " WHERE p.id = ?", (specimen_id,)).fetchone())
    if not row:
        not_found("Spécimen")
    if row["species_id"]:
        row["species"] = get_species_row(conn, row["species_id"])
    row["zones"] = []
    if row["lat"] is not None:
        polys = [db.row_to_dict(z) for z in conn.execute("SELECT id, kind, name, geometry FROM zones")]
        hits = [z for z in polys if geo.point_in_polygon(row["lon"], row["lat"], z["geometry"])]
        hits.sort(key=lambda z: geo.measure(z["geometry"]).get("area_m2", 0))  # la plus petite d'abord
        row["zones"] = [{"id": z["id"], "kind": z["kind"], "name": z["name"]} for z in hits]
    row["photos"] = [
        dict(r) for r in conn.execute(
            "SELECT * FROM photos WHERE specimen_id = ? ORDER BY taken_at, id", (specimen_id,)
        ).fetchall()
    ]
    row["events"] = [
        db.row_to_dict(r) for r in conn.execute(
            "SELECT * FROM events WHERE specimen_id = ? ORDER BY date DESC, id DESC", (specimen_id,)
        ).fetchall()
    ]
    row["positions"] = [
        dict(r) for r in conn.execute(
            "SELECT * FROM positions WHERE specimen_id = ? ORDER BY moved_at DESC, id DESC", (specimen_id,)
        ).fetchall()
    ]
    return row


@app.get("/api/specimens")
def list_specimens():
    with db.tx() as c:
        rows = c.execute(SPECIMEN_LIST_SQL + " ORDER BY COALESCE(p.nickname, s.common_name) COLLATE NOCASE").fetchall()
    return [db.row_to_dict(r) for r in rows]


@app.get("/api/specimens/{specimen_id}")
def get_specimen(specimen_id: int):
    with db.tx() as c:
        return get_specimen_full(c, specimen_id)


@app.post("/api/specimens", status_code=201)
def create_specimen(payload: dict = Body(...)):
    vals = _specimen_values(payload, None)
    if not vals["species_id"] and not vals["nickname"]:
        raise HTTPException(400, "Choisissez une espèce ou donnez un nom.")
    now = db.now_iso()
    cols = list(vals.keys())
    with db.tx() as c:
        cur = c.execute(
            f"INSERT INTO specimens({', '.join(cols)}, created_at, updated_at) "
            f"VALUES ({', '.join(':' + k for k in cols)}, :now, :now)",
            {**vals, "now": now},
        )
        sid = cur.lastrowid
        if vals["lat"] is not None:
            c.execute(
                "INSERT INTO positions(specimen_id, lat, lon, moved_at, reason) VALUES (?, ?, ?, ?, 'création')",
                (sid, vals["lat"], vals["lon"], now),
            )
        return get_specimen_full(c, sid)


@app.put("/api/specimens/{specimen_id}")
def update_specimen(specimen_id: int, payload: dict = Body(...)):
    with db.tx() as c:
        existing = get_specimen_full(c, specimen_id)
        vals = _specimen_values(payload, existing)
        sets = ", ".join(f"{k} = :{k}" for k in vals)
        now = db.now_iso()
        c.execute(f"UPDATE specimens SET {sets}, updated_at = :now WHERE id = :id", {**vals, "now": now, "id": specimen_id})
        moved = vals["lat"] is not None and (vals["lat"], vals["lon"]) != (existing["lat"], existing["lon"])
        if moved:
            c.execute(
                "INSERT INTO positions(specimen_id, lat, lon, moved_at, reason) VALUES (?, ?, ?, ?, ?)",
                (specimen_id, vals["lat"], vals["lon"], now, payload.get("move_reason") or "déplacement"),
            )
        return get_specimen_full(c, specimen_id)


@app.post("/api/specimens/{specimen_id}/duplicate", status_code=201)
def duplicate_specimen(specimen_id: int, payload: dict = Body(default={})):
    with db.tx() as c:
        src = get_specimen_full(c, specimen_id)
    copy = {k: src.get(k) for k in SPECIMEN_FIELDS} | {"tags": src.get("tags", [])}
    copy.update({k: payload[k] for k in ("lat", "lon", "gps_accuracy", "position_source", "nickname") if k in payload})
    return create_specimen(copy)


@app.delete("/api/specimens/{specimen_id}", status_code=204)
def delete_specimen(specimen_id: int):
    with db.tx() as c:
        sp = get_specimen_full(c, specimen_id)
        c.execute("DELETE FROM specimens WHERE id = ?", (specimen_id,))
    for p in sp["photos"]:
        photos.delete_files(db.PHOTO_DIR, specimen_id, p["filename"], p["ext"])


# ---------------------------------------------------------------------------
# Photos
# ---------------------------------------------------------------------------
@app.post("/api/specimens/{specimen_id}/photos", status_code=201)
async def upload_photos(
    specimen_id: int,
    files: list[UploadFile] = File(...),
    fallback_dates: str = Form("[]"),
    caption: str = Form(""),
):
    """fallback_dates : dates locales ISO (une par fichier) utilisées si l'EXIF n'en donne pas,
    calculées par le navigateur à partir de la date du fichier."""
    with db.tx() as c:
        get_specimen_full(c, specimen_id)
    try:
        fallbacks = json.loads(fallback_dates)
    except json.JSONDecodeError:
        fallbacks = []
    max_side = int(options().get("photo_max_size", 2000))
    created, errors = [], []
    for i, f in enumerate(files):
        data = await f.read()
        try:
            info = photos.process_upload(data, f.filename or "photo.jpg", db.PHOTO_DIR / str(specimen_id), max_side)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if info["taken_at"]:
            taken, source = info["taken_at"], "exif"
        elif i < len(fallbacks) and fallbacks[i]:
            taken, source = str(fallbacks[i])[:19], "import"
        else:
            taken, source = datetime.now().replace(microsecond=0).isoformat(), "import"
        with db.tx() as c:
            cur = c.execute(
                "INSERT INTO photos(specimen_id, filename, ext, taken_at, taken_source, imported_at, caption, width, height) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (specimen_id, info["filename"], info["ext"], taken, source, db.now_iso(), caption or None, info["width"], info["height"]),
            )
            created.append(dict(c.execute("SELECT * FROM photos WHERE id = ?", (cur.lastrowid,)).fetchone()))
    if not created and errors:
        raise HTTPException(400, "; ".join(errors))
    return {"photos": created, "errors": errors}


def _photo(conn, photo_id: int) -> dict:
    row = conn.execute("SELECT * FROM photos WHERE id = ?", (photo_id,)).fetchone()
    if not row:
        not_found("Photo")
    return dict(row)


@app.get("/api/photos/{photo_id}/{size}")
def get_photo(photo_id: int, size: str):
    if size not in photos.SIZES:
        raise HTTPException(400, "Taille inconnue")
    with db.tx() as c:
        p = _photo(c, photo_id)
    path = photos.photo_path(db.PHOTO_DIR, p["specimen_id"], p["filename"], p["ext"], size)
    if not path.exists():
        not_found("Fichier photo")
    return FileResponse(path, headers={"Cache-Control": "max-age=31536000, immutable"})


@app.put("/api/photos/{photo_id}")
def update_photo(photo_id: int, payload: dict = Body(...)):
    with db.tx() as c:
        p = _photo(c, photo_id)
        taken, source = p["taken_at"], p["taken_source"]
        if payload.get("taken_at"):
            taken, source = str(payload["taken_at"])[:19], "manual"
        caption = payload["caption"] if "caption" in payload else p["caption"]
        c.execute("UPDATE photos SET taken_at = ?, taken_source = ?, caption = ? WHERE id = ?", (taken, source, caption or None, photo_id))
        return _photo(c, photo_id)


@app.delete("/api/photos/{photo_id}", status_code=204)
def delete_photo(photo_id: int):
    with db.tx() as c:
        p = _photo(c, photo_id)
        c.execute("DELETE FROM photos WHERE id = ?", (photo_id,))
    photos.delete_files(db.PHOTO_DIR, p["specimen_id"], p["filename"], p["ext"])


# ---------------------------------------------------------------------------
# Journal : interventions, observations, mesures
# ---------------------------------------------------------------------------
EVENT_FIELDS = ("kind", "date", "type", "title", "notes", "product", "quantity", "value", "unit", "severity", "status", "photo_id", "diagnosis")
EVENT_KINDS = {"intervention", "observation", "measure"}
DIAG_MAX_PHOTOS = 4
DIAG_IMAGE_SIDE = 1568  # au-delà, l'API réduit l'image elle-même : inutile d'envoyer plus


def _event_values(payload: dict, existing: dict | None) -> dict:
    vals = {k: (payload.get(k) if k in payload else (existing or {}).get(k)) for k in EVENT_FIELDS}
    vals = {k: (None if v == "" else v) for k, v in vals.items()}
    if vals["kind"] not in EVENT_KINDS:
        raise HTTPException(400, "Type d'entrée inconnu")
    if not vals["date"]:
        raise HTTPException(400, "La date est obligatoire")
    if vals["kind"] == "observation" and not vals["status"]:
        vals["status"] = "ouvert"
    if vals["value"] is not None:
        try:
            vals["value"] = float(vals["value"])
        except (TypeError, ValueError):
            raise HTTPException(400, "Valeur de mesure invalide")
    d = vals["diagnosis"]
    if d is not None and not isinstance(d, str):
        if not isinstance(d, dict):
            raise HTTPException(400, "Diagnostic invalide")
        vals["diagnosis"] = json.dumps(d, ensure_ascii=False)
    return vals


def _event(conn, event_id: int) -> dict:
    row = db.row_to_dict(conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone())
    if not row:
        not_found("Entrée du journal")
    return row


@app.post("/api/specimens/{specimen_id}/events", status_code=201)
def create_event(specimen_id: int, payload: dict = Body(...)):
    vals = _event_values(payload, None)
    with db.tx() as c:
        get_specimen_full(c, specimen_id)
        cols = list(vals.keys())
        cur = c.execute(
            f"INSERT INTO events(specimen_id, {', '.join(cols)}, created_at) VALUES (:sid, {', '.join(':' + k for k in cols)}, :now)",
            {**vals, "sid": specimen_id, "now": db.now_iso()},
        )
        return _event(c, cur.lastrowid)


@app.put("/api/events/{event_id}")
def update_event(event_id: int, payload: dict = Body(...)):
    with db.tx() as c:
        existing = _event(c, event_id)
        if isinstance(existing.get("diagnosis"), dict):
            existing["diagnosis"] = json.dumps(existing["diagnosis"], ensure_ascii=False)
        vals = _event_values(payload, existing)
        c.execute(f"UPDATE events SET {', '.join(f'{k} = :{k}' for k in vals)} WHERE id = :id", {**vals, "id": event_id})
        return _event(c, event_id)


@app.delete("/api/events/{event_id}", status_code=204)
def delete_event(event_id: int):
    with db.tx() as c:
        c.execute("DELETE FROM events WHERE id = ?", (event_id,))


def _diag_image(photo: dict) -> str:
    """Version réduite en JPEG base64, prête à envoyer au modèle."""
    path = photos.photo_path(db.PHOTO_DIR, photo["specimen_id"], photo["filename"], photo["ext"], "md")
    if not path.exists():
        not_found("Fichier photo")
    img = Image.open(path)
    img.thumbnail((DIAG_IMAGE_SIDE, DIAG_IMAGE_SIDE), Image.Resampling.LANCZOS)
    if img.mode != "RGB":
        img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()


@app.post("/api/events/{event_id}/diagnose")
async def diagnose_event(event_id: int, payload: dict = Body(default={})):
    """Diagnostic par IA d'un problème du journal. Ne modifie rien : le résultat est enregistré
    ensuite par PUT /api/events/{id} avec le champ diagnosis, si l'utilisateur le souhaite."""
    with db.tx() as c:
        ev = _event(c, event_id)
        if ev["kind"] != "observation":
            raise HTTPException(400, "Le diagnostic concerne les problèmes du journal.")
        sp = get_specimen_full(c, ev["specimen_id"])
        ids = [int(i) for i in (payload.get("photo_ids") or [])] or ([ev["photo_id"]] if ev["photo_id"] else [])
        if not ids:
            raise HTTPException(400, "Choisissez au moins une photo du problème.")
        if len(ids) > DIAG_MAX_PHOTOS:
            raise HTTPException(400, f"{DIAG_MAX_PHOTOS} photos au maximum.")
        chosen = [_photo(c, i) for i in ids]
    if any(p["specimen_id"] != sp["id"] for p in chosen):
        raise HTTPException(400, "Ces photos n'appartiennent pas à cette plante.")

    description = " — ".join(x for x in (ev.get("type"), ev.get("title"), ev.get("notes")) if x)
    history = [
        {k: e[k] for k in ("date", "kind", "type", "title", "product") if e.get(k)}
        for e in sp["events"] if e["id"] != event_id
    ][:10]
    age = None
    if sp.get("planted_on"):
        age = round((datetime.now() - datetime.fromisoformat(sp["planted_on"])).days / 365.25, 1)
    elif sp.get("age_years") is not None:
        age = sp["age_years"]
    ctx = {
        "nickname": sp.get("nickname"), "species": sp.get("species"), "age_years": age,
        "exposure": sp.get("exposure"), "soil": sp.get("soil"),
        "zone": ", ".join(geo.KIND_BY_KEY[z["kind"]]["label"] + (f" « {z['name']} »" if z["name"] else "") for z in sp["zones"]) or None,
        "date": ev["date"], "description": description, "history": history,
    }
    images = [_diag_image(p) for p in chosen]
    try:
        result = await ai.diagnose(options(), ctx, images)
    except ai.AIError as exc:
        raise HTTPException(502, str(exc))
    except Exception as exc:
        raise HTTPException(502, f"Appel à l'IA impossible : {exc}")
    return {**result, "photo_ids": ids, "generated_at": db.now_iso()}


# ---------------------------------------------------------------------------
# Position via l'app compagnon Home Assistant
# ---------------------------------------------------------------------------
@app.get("/api/ha/trackers")
async def trackers():
    try:
        return await ha.list_trackers()
    except Exception as exc:
        raise HTTPException(502, f"API Home Assistant indisponible : {exc}")


@app.get("/api/ha/position")
async def tracker_position():
    entity = db.get_setting("tracker_entity")
    if not entity:
        raise HTTPException(400, "Aucun appareil choisi dans les réglages.")
    try:
        t = await ha.get_tracker(entity)
    except Exception as exc:
        raise HTTPException(502, f"API Home Assistant indisponible : {exc}")
    if not t:
        raise HTTPException(404, f"{entity} n'a pas de position GPS.")
    return t


# ---------------------------------------------------------------------------
# Export complet
# ---------------------------------------------------------------------------
@app.get("/api/export")
def export_all():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        conn = db.connect()
        try:
            backup = db.DATA_DIR / "export_tmp.db"
            dest = sqlite3.connect(backup)
            conn.backup(dest)
            dest.close()
        finally:
            conn.close()
        z.write(backup, "gardenmap.db")
        backup.unlink(missing_ok=True)
        with db.tx() as c:
            zones = [db.row_to_dict(r) for r in c.execute("SELECT * FROM zones")]
        fc = {"type": "FeatureCollection", "features": [
            {"type": "Feature", "geometry": zz["geometry"], "properties": {"id": zz["id"], "kind": zz["kind"], "name": zz["name"]}}
            for zz in zones]}
        z.writestr("zones.geojson", json.dumps(fc, ensure_ascii=False, indent=1))
        for f in db.PHOTO_DIR.rglob("*"):
            if f.is_file():
                z.write(f, f"photos/{f.relative_to(db.PHOTO_DIR)}")
    buf.seek(0)
    name = f"gardenmap-{datetime.now():%Y%m%d}.zip"
    return StreamingResponse(buf, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{name}"'})


# ---------------------------------------------------------------------------
# Interface web
# ---------------------------------------------------------------------------
@app.api_route("/api/{rest:path}", methods=["GET", "POST", "PUT", "DELETE"])
def api_404(rest: str):
    not_found("Route d'API")


if (STATIC_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")


@app.get("/{path:path}")
def spa(path: str):
    target = STATIC_DIR / path
    if path and target.is_file() and STATIC_DIR.resolve() in target.resolve().parents:
        return FileResponse(target)
    index = STATIC_DIR / "index.html"
    if not index.exists():
        return JSONResponse({"detail": "Interface non construite"}, status_code=503)
    return FileResponse(index, headers={"Cache-Control": "no-cache"})
