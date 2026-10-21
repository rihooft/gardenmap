"""Tests de bout en bout de l'API (lancer depuis le dossier gardenmap/ : python -m pytest backend/tests)."""
import asyncio
import io
import json
import math
import os
import tempfile

import pytest

TMP = tempfile.mkdtemp(prefix="gardenmap-test-")
os.environ["GARDENMAP_DATA"] = TMP

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

from backend import ai  # noqa: E402
from backend import geo  # noqa: E402
from backend.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def jpeg_bytes(w=800, h=600, color=(40, 120, 40), exif_date=None) -> bytes:
    img = Image.new("RGB", (w, h), color)
    buf = io.BytesIO()
    if exif_date:
        exif = Image.Exif()
        exif.get_ifd(0x8769)[36867] = exif_date
        img.save(buf, "JPEG", exif=exif.tobytes())
    else:
        img.save(buf, "JPEG")
    return buf.getvalue()


# ---------------------------------------------------------------- géométrie
REF = (48.8350, 2.5200)


def gps_offset(north_m, east_m):
    lat = REF[0] + north_m / 111195.0
    lon = REF[1] + east_m / (111195.0 * math.cos(math.radians(REF[0])))
    return lat, lon


def square(n0, e0, size):
    """Carré de size mètres, coin sud-ouest à (n0, e0) mètres de REF, en GeoJSON lon/lat."""
    pts = [gps_offset(n0, e0), gps_offset(n0, e0 + size), gps_offset(n0 + size, e0 + size), gps_offset(n0 + size, e0)]
    return {"type": "Polygon", "coordinates": [[[lon, lat] for lat, lon in pts]]}


def test_measures():
    assert geo.measure(geo.clean_geometry(square(0, 0, 10), "polygon"))["area_m2"] == pytest.approx(100, rel=1e-3)
    a, b = gps_offset(0, 0), gps_offset(30, 40)
    line = {"type": "LineString", "coordinates": [[a[1], a[0]], [b[1], b[0]]]}
    assert geo.measure(geo.clean_geometry(line, "line"))["length_m"] == pytest.approx(50, rel=1e-3)
    lat, lon = gps_offset(5, 5)
    assert geo.point_in_polygon(lon, lat, geo.clean_geometry(square(0, 0, 10), "polygon"))
    lat, lon = gps_offset(15, 5)
    assert not geo.point_in_polygon(lon, lat, geo.clean_geometry(square(0, 0, 10), "polygon"))


def test_geometry_validation():
    sq = square(0, 0, 10)
    open_ring = {"type": "Polygon", "coordinates": [sq["coordinates"][0][:-1]]}
    assert geo.clean_geometry(open_ring, "polygon")["coordinates"][0][0] == geo.clean_geometry(open_ring, "polygon")["coordinates"][0][-1]
    for bad in [{"type": "Polygon", "coordinates": [[[2.5, 48.8], [2.5, 48.8]]]},
                {"type": "Point", "coordinates": [2.5, 48.8]},
                {"type": "Polygon", "coordinates": [[[200, 48], [2, 48], [2, 49]]]},
                {"type": "Polygon", "coordinates": [[["a", 48], [2, 48], [2, 49]]]}]:
        with pytest.raises(geo.GeometryError):
            geo.clean_geometry(bad, "polygon")
    with pytest.raises(geo.GeometryError):
        geo.clean_geometry(sq, "line")


# ---------------------------------------------------------------- API
def test_meta_and_empty_state(client):
    r = client.get("/api/meta")
    assert r.status_code == 200
    m = r.json()
    assert any(f["key"] == "hardiness_c" for f in m["species_fields"])
    assert m["ai_enabled"] is False
    assert client.get("/api/garden").json() is None
    assert any(k["key"] == "pelouse" for k in m["zone_kinds"])
    assert client.get("/api/specimens").json() == []


def test_full_flow(client):
    # emplacement du jardin
    r = client.put("/api/garden", json={"lat": REF[0], "lon": REF[1], "zoom": 25, "label": "Maison"})
    assert r.status_code == 200 and r.json()["zoom"] == 22
    assert client.put("/api/garden", json={"lat": 120, "lon": 2}).status_code == 400
    assert client.get("/api/meta").json()["garden"]["label"] == "Maison"

    # zones : grande pelouse, massif dedans, mur
    lawn = client.post("/api/zones", json={"kind": "pelouse", "name": "Pelouse", "geometry": square(0, 0, 40)}).json()
    assert lawn["area_m2"] == pytest.approx(1600, rel=1e-3)
    bed = client.post("/api/zones", json={"kind": "massif", "name": "Massif du figuier", "geometry": square(25, 35, 10)}).json()
    a_, b_ = gps_offset(0, 0), gps_offset(0, 40)
    wall = client.post("/api/zones", json={"kind": "mur", "geometry": {"type": "LineString", "coordinates": [[a_[1], a_[0]], [b_[1], b_[0]]]}})
    assert wall.status_code == 201 and wall.json()["length_m"] == pytest.approx(40, rel=1e-3)
    assert client.post("/api/zones", json={"kind": "mur", "geometry": square(0, 0, 5)}).status_code == 400
    assert client.post("/api/zones", json={"kind": "inconnu", "geometry": square(0, 0, 5)}).status_code == 400
    assert client.put(f"/api/zones/{lawn['id']}", json={"kind": "mur"}).status_code == 400
    r = client.put(f"/api/zones/{bed['id']}", json={"kind": "potager"})
    assert r.json()["kind"] == "potager" and r.json()["name"] == "Massif du figuier"
    client.put(f"/api/zones/{bed['id']}", json={"kind": "massif"})
    assert len(client.get("/api/zones").json()) == 3

    # espèce
    r = client.post("/api/species", json={"common_name": "Figuier", "botanical_name": "Ficus carica", "category": "fruitier",
                                          "attrs": {"hardiness_c": "-12", "exposure": ["soleil"], "flowering_months": [6, 7, 13], "bogus": 1}})
    assert r.status_code == 201, r.text
    sp = r.json()
    assert sp["attrs"] == {"hardiness_c": -12.0, "exposure": ["Soleil"], "flowering_months": [6, 7]}

    # spécimen placé dans le massif (lui-même dans la pelouse)
    lat, lon = gps_offset(30, 40)
    r = client.post("/api/specimens", json={"species_id": sp["id"], "lat": lat, "lon": lon, "position_source": "manual", "tags": ["verger"]})
    assert r.status_code == 201, r.text
    s = r.json()
    assert len(s["positions"]) == 1 and s["common_name"] == "Figuier"
    assert [z["name"] for z in s["zones"]] == ["Massif du figuier", "Pelouse"]
    assert client.post("/api/specimens", json={"nickname": "x", "lat": lat}).status_code == 400

    # déplacement -> historique
    lat2, lon2 = gps_offset(30, 42)
    r = client.put(f"/api/specimens/{s['id']}", json={"lat": lat2, "lon": lon2, "move_reason": "transplantation"})
    assert len(r.json()["positions"]) == 2
    assert r.json()["positions"][0]["reason"] == "transplantation"
    # modification sans déplacement -> pas de nouvelle position
    r = client.put(f"/api/specimens/{s['id']}", json={"notes": "Planté près du mur"})
    assert len(r.json()["positions"]) == 2 and r.json()["notes"] == "Planté près du mur"

    # photos : EXIF puis date de repli
    files = [("files", ("a.jpg", jpeg_bytes(3000, 2000, exif_date="2024:05:12 10:30:00"), "image/jpeg")),
             ("files", ("b.jpg", jpeg_bytes(), "image/jpeg")),
             ("files", ("c.txt", b"pas une image", "text/plain"))]
    r = client.post(f"/api/specimens/{s['id']}/photos", files=files, data={"fallback_dates": json.dumps([None, "2025-08-01T18:00:00", None])})
    assert r.status_code == 201, r.text
    body = r.json()
    assert [p["taken_at"] for p in body["photos"]] == ["2024-05-12T10:30:00", "2025-08-01T18:00:00"]
    assert [p["taken_source"] for p in body["photos"]] == ["exif", "import"]
    assert len(body["errors"]) == 1
    pid = body["photos"][0]["id"]
    for size in ("th", "md", "orig"):
        assert client.get(f"/api/photos/{pid}/{size}").status_code == 200
    md = Image.open(io.BytesIO(client.get(f"/api/photos/{pid}/md").content))
    assert max(md.size) == 2000
    r = client.put(f"/api/photos/{pid}", json={"taken_at": "2024-05-11T09:00:00", "caption": "Plantation"})
    assert r.json()["taken_source"] == "manual"

    # journal
    r = client.post(f"/api/specimens/{s['id']}/events", json={"kind": "observation", "date": "2026-06-01", "type": "maladie", "title": "Rouille"})
    assert r.status_code == 201 and r.json()["status"] == "ouvert"
    eid = r.json()["id"]
    client.post(f"/api/specimens/{s['id']}/events", json={"kind": "measure", "date": "2026-06-01", "type": "hauteur", "value": "2,5".replace(",", "."), "unit": "m"})
    lst = client.get("/api/specimens").json()
    assert lst[0]["open_issues"] == 1 and lst[0]["photo_count"] == 2
    client.put(f"/api/events/{eid}", json={"status": "resolu"})
    assert client.get("/api/specimens").json()[0]["open_issues"] == 0

    # duplication pour une haie
    lat3, lon3 = gps_offset(10, 10)
    r = client.post(f"/api/specimens/{s['id']}/duplicate", json={"lat": lat3, "lon": lon3})
    assert r.status_code == 201 and r.json()["species_id"] == sp["id"] and r.json()["lat"] == pytest.approx(lat3)
    assert [z["name"] for z in r.json()["zones"]] == ["Pelouse"]
    assert r.json()["photo_count"] == 0

    # espèce utilisée : suppression refusée
    assert client.delete(f"/api/species/{sp['id']}").status_code == 409

    # export
    r = client.get("/api/export")
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    import zipfile as zf
    names = zf.ZipFile(io.BytesIO(r.content)).namelist()
    assert "gardenmap.db" in names and "zones.geojson" in names
    assert len(json.loads(zf.ZipFile(io.BytesIO(r.content)).read("zones.geojson"))["features"]) == 3
    assert client.delete(f"/api/zones/{bed['id']}").status_code == 204

    # suppression d'un spécimen et de ses fichiers
    assert client.delete(f"/api/specimens/{s['id']}").status_code == 204
    assert client.get(f"/api/photos/{pid}/th").status_code == 404


def test_ai_enrich_never_overwrites(client, monkeypatch):
    sp = client.post("/api/species", json={"common_name": "Laurier-rose", "attrs": {"hardiness_c": -8}}).json()
    # une valeur proposée par l'IA puis validée par l'utilisateur
    client.put(f"/api/species/{sp['id']}", json={"attrs": {"hardiness_c": -8, "foliage": "Persistant"},
                                                 "attr_meta": {"foliage": {"source": "IA · test", "pending": False}}})

    async def fake_call(opts, system, parts, max_tokens):
        prompt = parts[-1]["text"]
        assert "Laurier-rose" in prompt
        return "Voici :\n```json\n" + json.dumps({
            "botanical_name": "Nerium oleander", "hardiness_c": -12, "foliage": "Caduc",
            "toxicity": "Très toxique pour l'homme et les animaux.", "flowering_months": [6, 7, 8, 9],
            "water_need": "faible", "growth_rate": "inconnue", "confidence": "haute"}) + "\n```"

    monkeypatch.setattr("backend.main.options", lambda: {"ai_provider": "anthropic", "ai_api_key": "x"})
    real = ai.enrich
    monkeypatch.setattr("backend.main.ai.enrich", lambda opts, s: real(opts, s, call=fake_call))
    r = client.post(f"/api/species/{sp['id']}/enrich")
    assert r.status_code == 200, r.text
    props = r.json()["proposals"]
    assert "hardiness_c" not in props          # saisie à la main
    assert "foliage" not in props              # validée
    assert "growth_rate" not in props          # valeur hors liste
    assert props["botanical_name"] == "Nerium oleander"
    assert props["water_need"] == "Faible" and props["flowering_months"] == [6, 7, 8, 9]
    assert r.json()["confidence"] == "haute"


def test_ai_not_configured(client):
    sp = client.post("/api/species", json={"common_name": "Rosier"}).json()
    r = client.post(f"/api/species/{sp['id']}/enrich")
    assert r.status_code == 502 and "fournisseur" in r.json()["detail"]


def test_extract_json_variants():
    assert ai.extract_json('{"a": 1}') == {"a": 1}
    assert ai.extract_json('blabla {"a": {"b": 2}} fin') == {"a": {"b": 2}}
    with pytest.raises(ai.AIError):
        ai.extract_json("rien")


def test_ingress_only(client, monkeypatch):
    from starlette.testclient import TestClient as TC
    with TC(app, client=("8.8.8.8", 1234)) as c:
        assert c.get("/api/meta").status_code == 403


def test_diagnosis(client, monkeypatch):
    sp = client.post("/api/species", json={"common_name": "Rosier", "botanical_name": "Rosa", "attrs": {"diseases": "Marsonia, oïdium"}}).json()
    s = client.post("/api/specimens", json={"species_id": sp["id"], "lat": REF[0], "lon": REF[1], "exposure": "Mi-ombre", "planted_on": "2022-03-01"}).json()
    up = client.post(f"/api/specimens/{s['id']}/photos", files=[
        ("files", ("f1.jpg", jpeg_bytes(3000, 2000, color=(30, 90, 30)), "image/jpeg")),
        ("files", ("f2.jpg", jpeg_bytes(900, 600), "image/jpeg"))]).json()["photos"]
    client.post(f"/api/specimens/{s['id']}/events", json={"kind": "intervention", "date": "2026-05-01", "type": "Traitement", "product": "purin d'ortie"})
    ev = client.post(f"/api/specimens/{s['id']}/events", json={"kind": "observation", "date": "2026-07-14", "type": "Maladie",
                                                                "title": "Taches noires sur les feuilles", "photo_id": up[0]["id"]}).json()
    seen = {}

    async def fake_call(opts, system, parts, max_tokens):
        seen["images"] = [p for p in parts if p["type"] == "image"]
        seen["prompt"] = parts[-1]["text"]
        seen["system"] = system
        return json.dumps({
            "plant_visible": True, "symptoms": "Taches noires à bord frangé, jaunissement autour.",
            "hypotheses": [
                {"name": "Maladie des taches noires (Diplocarpon rosae)", "type": "maladie", "confidence": "Haute",
                 "evidence": "taches rondes à bord frangé", "check": "Regarder le revers des feuilles basses",
                 "actions": ["Ramasser les feuilles tombées", "Pulvériser une décoction de prêle"], "prevention": "Arroser au pied"},
                {"name": "Carence en magnésium", "type": "deficit", "confidence": "très faible", "actions": "Apport de sulfate de magnésium"},
                {"type": "maladie"}],
            "urgency": "Moyenne", "advice": "Photographier aussi le revers d'une feuille."})

    # pas de fournisseur configuré
    r = client.post(f"/api/events/{ev['id']}/diagnose", json={})
    assert r.status_code == 502

    monkeypatch.setattr("backend.main.options", lambda: {"ai_provider": "anthropic", "ai_api_key": "x"})
    real = ai.diagnose
    monkeypatch.setattr("backend.main.ai.diagnose", lambda opts, ctx, imgs: real(opts, ctx, imgs, call=fake_call))

    # photo jointe à l'observation, utilisée par défaut
    r = client.post(f"/api/events/{ev['id']}/diagnose", json={})
    assert r.status_code == 200, r.text
    d = r.json()
    assert len(seen["images"]) == 1
    img = Image.open(io.BytesIO(__import__("base64").b64decode(seen["images"][0]["data"])))
    assert max(img.size) == 1568
    assert "Rosier" in seen["prompt"] and "été" in seen["prompt"] and "Mi-ombre" in seen["prompt"]
    assert "Taches noires sur les feuilles" in seen["prompt"] and "purin d'ortie" in seen["prompt"]
    assert "Marsonia" in seen["prompt"] and "2019" in seen["system"]
    assert [h["confidence"] for h in d["hypotheses"]] == ["haute", "faible"]
    assert d["hypotheses"][1]["type"] == "autre" and d["hypotheses"][1]["actions"] == ["Apport de sulfate de magnésium"]
    assert d["urgency"] == "moyenne" and d["photo_ids"] == [up[0]["id"]]

    # plusieurs photos choisies
    r = client.post(f"/api/events/{ev['id']}/diagnose", json={"photo_ids": [up[0]["id"], up[1]["id"]]})
    assert r.status_code == 200 and len(seen["images"]) == 2

    # enregistrement du diagnostic dans le journal
    r = client.put(f"/api/events/{ev['id']}", json={"diagnosis": d, "title": d["hypotheses"][0]["name"]})
    assert r.status_code == 200 and r.json()["diagnosis"]["hypotheses"][0]["confidence"] == "haute"
    full = client.get(f"/api/specimens/{s['id']}").json()
    saved = [e for e in full["events"] if e["id"] == ev["id"]][0]
    assert saved["diagnosis"]["urgency"] == "moyenne" and saved["title"].startswith("Maladie des taches noires")
    # une autre modification ne perd pas le diagnostic
    r = client.put(f"/api/events/{ev['id']}", json={"status": "resolu"})
    assert r.json()["diagnosis"]["advice"]

    # refus : intervention, photo d'une autre plante, aucune photo
    other = client.post("/api/specimens", json={"nickname": "Autre"}).json()
    op = client.post(f"/api/specimens/{other['id']}/photos", files=[("files", ("o.jpg", jpeg_bytes(), "image/jpeg"))]).json()["photos"][0]
    assert client.post(f"/api/events/{ev['id']}/diagnose", json={"photo_ids": [op["id"]]}).status_code == 400
    ev2 = client.post(f"/api/specimens/{s['id']}/events", json={"kind": "observation", "date": "2026-07-15", "type": "Ravageur"}).json()
    assert client.post(f"/api/events/{ev2['id']}/diagnose", json={}).status_code == 400
    inter = [e for e in full["events"] if e["kind"] == "intervention"][0]
    assert client.post(f"/api/events/{inter['id']}/diagnose", json={"photo_ids": [up[0]["id"]]}).status_code == 400


def test_migration_adds_diagnosis_column(tmp_path):
    import sqlite3
    from backend import db
    old = sqlite3.connect(tmp_path / "old.db")
    old.executescript(db.SCHEMA.replace("    diagnosis    TEXT,               -- diagnostic IA enregistré (JSON)\n", ""))
    assert "diagnosis" not in {r[1] for r in old.execute("PRAGMA table_info(events)")}
    old.row_factory = sqlite3.Row
    db.migrate(old)
    assert "diagnosis" in {r[1] for r in old.execute("PRAGMA table_info(events)")}
    db.migrate(old)  # idempotent


def test_geocode(client, monkeypatch):
    class FakeResp:
        status_code = 200
        def raise_for_status(self): pass
        def json(self):
            return {"features": [{"geometry": {"coordinates": [2.52, 48.835]}, "properties": {"label": "1 Rue X 94360 Bry-sur-Marne", "type": "housenumber"}},
                                 {"geometry": None, "properties": {}}]}

    class FakeClient:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def get(self, url, params=None):
            assert params["q"] == "1 rue x bry"
            return FakeResp()

    monkeypatch.setattr("backend.main.httpx.AsyncClient", FakeClient)
    r = client.get("/api/geocode", params={"q": " 1 rue x bry "})
    assert r.status_code == 200 and r.json() == [{"label": "1 Rue X 94360 Bry-sur-Marne", "lat": 48.835, "lon": 2.52, "type": "housenumber"}]
    assert client.get("/api/geocode", params={"q": "ab"}).json() == []


def test_custom_source(client):
    assert client.put("/api/settings/custom-source", json={"url": "http://x/{z}/{x}/{y}.png"}).status_code == 400
    r = client.put("/api/settings/custom-source", json={"url": "https://tiles.example/{z}/{x}.png"})
    assert r.status_code == 400 and "{y}" in r.json()["detail"]
    r = client.put("/api/settings/custom-source", json={"url": "https://tiles.example/{z}/{x}/{y}.jpg", "native": 30, "label": "Essai"})
    assert r.json()["custom_source"] == {"label": "Essai", "url": "https://tiles.example/{z}/{x}/{y}.jpg", "native": 23, "attribution": ""}
    assert client.get("/api/meta").json()["custom_source"]["label"] == "Essai"
    assert client.put("/api/settings/custom-source", json={"url": ""}).json()["custom_source"] is None
