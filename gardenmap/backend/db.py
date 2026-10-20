"""Accès SQLite : schéma versionné et petites fonctions utilitaires."""
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(os.environ.get("GARDENMAP_DATA", "/data"))
DB_PATH = DATA_DIR / "gardenmap.db"
PHOTO_DIR = DATA_DIR / "photos"

SCHEMA_VERSION = 3

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS species (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    common_name    TEXT NOT NULL,
    botanical_name TEXT,
    cultivar       TEXT,
    family         TEXT,
    category       TEXT,
    attrs          TEXT NOT NULL DEFAULT '{}',   -- attributs botaniques (JSON)
    attr_meta      TEXT NOT NULL DEFAULT '{}',   -- par champ : source, date, à valider (JSON)
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS specimens (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    species_id       INTEGER REFERENCES species(id) ON DELETE SET NULL,
    nickname         TEXT,
    x                REAL,           -- inutilisé depuis la v3 (ancien plan image)
    y                REAL,
    lat              REAL,           -- position WGS84
    lon              REAL,
    gps_accuracy     REAL,           -- mètres
    position_source  TEXT,           -- gps, manual, coords, tracker
    planted_on       TEXT,           -- date ISO
    age_years        REAL,           -- âge estimé…
    age_estimated_on TEXT,           -- …à cette date
    origin           TEXT,
    status           TEXT NOT NULL DEFAULT 'en_place',
    exposure         TEXT,
    soil             TEXT,
    irrigation_zone  TEXT,
    tags             TEXT NOT NULL DEFAULT '[]',
    notes            TEXT,
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS positions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    specimen_id  INTEGER NOT NULL REFERENCES specimens(id) ON DELETE CASCADE,
    x REAL, y REAL, lat REAL, lon REAL,
    moved_at     TEXT NOT NULL,
    reason       TEXT
);

CREATE TABLE IF NOT EXISTS photos (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    specimen_id  INTEGER NOT NULL REFERENCES specimens(id) ON DELETE CASCADE,
    filename     TEXT NOT NULL,      -- nom de base, sans suffixe de taille
    ext          TEXT NOT NULL,
    taken_at     TEXT NOT NULL,      -- date de prise de vue (EXIF) ou d'import
    taken_source TEXT NOT NULL,      -- exif, import, manual
    imported_at  TEXT NOT NULL,
    caption      TEXT,
    width        INTEGER,
    height       INTEGER
);

CREATE TABLE IF NOT EXISTS events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    specimen_id  INTEGER NOT NULL REFERENCES specimens(id) ON DELETE CASCADE,
    kind         TEXT NOT NULL,      -- intervention | observation | measure
    date         TEXT NOT NULL,
    type         TEXT,               -- taille, traitement, maladie, hauteur…
    title        TEXT,
    notes        TEXT,
    product      TEXT,
    quantity     TEXT,
    value        REAL,               -- mesures : valeur numérique
    unit         TEXT,
    severity     TEXT,               -- observations : faible, moyenne, forte
    status       TEXT,               -- observations : ouvert, resolu
    photo_id     INTEGER REFERENCES photos(id) ON DELETE SET NULL,
    diagnosis    TEXT,               -- diagnostic IA enregistré (JSON)
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS zones (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    kind        TEXT NOT NULL,       -- pelouse, massif, batiment, mur…  (voir geo.ZONE_KINDS)
    name        TEXT,
    geometry    TEXT NOT NULL,       -- GeoJSON (Polygon ou LineString), lon/lat WGS84
    notes       TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_specimens_species ON specimens(species_id);
CREATE INDEX IF NOT EXISTS idx_photos_specimen ON photos(specimen_id, taken_at);
CREATE INDEX IF NOT EXISTS idx_events_specimen ON events(specimen_id, date);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def tx():
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    with tx() as c:
        c.executescript(SCHEMA)
        migrate(c)
        c.execute(
            "INSERT OR IGNORE INTO settings(key, value) VALUES ('schema_version', ?)",
            (str(SCHEMA_VERSION),),
        )


def migrate(c: sqlite3.Connection) -> None:
    """Mises à jour de schéma pour les bases créées par une version précédente."""
    cols = {r["name"] for r in c.execute("PRAGMA table_info(events)")}
    if "diagnosis" not in cols:  # v2
        c.execute("ALTER TABLE events ADD COLUMN diagnosis TEXT")
    c.execute(
        "INSERT INTO settings(key, value) VALUES ('schema_version', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (str(SCHEMA_VERSION),),
    )


def get_setting(key: str, default=None):
    with tx() as c:
        row = c.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return json.loads(row["value"]) if row else default


def set_setting(key: str, value) -> None:
    with tx() as c:
        c.execute(
            "INSERT INTO settings(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, json.dumps(value)),
        )


JSON_COLUMNS = {"attrs", "attr_meta", "tags", "diagnosis", "geometry"}
EMPTY_JSON = {"attrs": {}, "attr_meta": {}, "tags": [], "diagnosis": None, "geometry": None}


def row_to_dict(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    d = dict(row)
    for k in JSON_COLUMNS & d.keys():
        try:
            d[k] = json.loads(d[k]) if d[k] else EMPTY_JSON[k]
        except (TypeError, json.JSONDecodeError):
            d[k] = EMPTY_JSON[k]
    return d
