"""Zones du jardin (aplats) : types, validation des géométries GeoJSON, surfaces et longueurs."""
import math

# kind -> libellé, couleur de l'aplat, type de géométrie, ordre d'affichage des lignes
ZONE_KINDS = [
    {"key": "pelouse", "label": "Pelouse", "color": "#a8cf6f", "geom": "polygon"},
    {"key": "prairie", "label": "Prairie, herbes hautes", "color": "#cbd98a", "geom": "polygon"},
    {"key": "massif", "label": "Massif fleuri", "color": "#e3b3cf", "geom": "polygon"},
    {"key": "bosquet", "label": "Arbres, bosquet", "color": "#5f9a58", "geom": "polygon"},
    {"key": "haie", "label": "Haie", "color": "#3f7c46", "geom": "polygon"},
    {"key": "potager", "label": "Potager", "color": "#bf9165", "geom": "polygon"},
    {"key": "verger", "label": "Verger", "color": "#8fbf6a", "geom": "polygon"},
    {"key": "terrasse", "label": "Terrasse", "color": "#dccaa6", "geom": "polygon"},
    {"key": "allee", "label": "Allée, gravier", "color": "#ece1c6", "geom": "polygon"},
    {"key": "batiment", "label": "Bâtiment", "color": "#b5aea6", "geom": "polygon"},
    {"key": "piscine", "label": "Piscine", "color": "#5fb6e6", "geom": "polygon"},
    {"key": "eau", "label": "Eau, mare", "color": "#79aecd", "geom": "polygon"},
    {"key": "autre", "label": "Autre surface", "color": "#d3d0c8", "geom": "polygon"},
    {"key": "mur", "label": "Mur", "color": "#6e6052", "geom": "line"},
    {"key": "cloture", "label": "Clôture", "color": "#7d7d7d", "geom": "line"},
    {"key": "bordure", "label": "Bordure, chemin", "color": "#a08b6c", "geom": "line"},
]
KIND_BY_KEY = {k["key"]: k for k in ZONE_KINDS}
MAX_VERTICES = 2000
R_EARTH = 6371008.8


class GeometryError(ValueError):
    pass


def _point(p) -> list[float]:
    if not isinstance(p, (list, tuple)) or len(p) < 2:
        raise GeometryError("Point invalide")
    try:
        lon, lat = float(p[0]), float(p[1])
    except (TypeError, ValueError):
        raise GeometryError("Coordonnée non numérique")
    if not (-180 <= lon <= 180 and -90 <= lat <= 90) or math.isnan(lon) or math.isnan(lat):
        raise GeometryError("Coordonnée hors limites")
    return [round(lon, 8), round(lat, 8)]


def clean_geometry(geom: dict, expected: str) -> dict:
    """Valide et normalise une géométrie GeoJSON (Polygon ou LineString), en lon/lat WGS84."""
    if not isinstance(geom, dict):
        raise GeometryError("Géométrie manquante")
    t = geom.get("type")
    coords = geom.get("coordinates")
    if expected == "polygon":
        if t != "Polygon" or not isinstance(coords, list) or not coords:
            raise GeometryError("Une surface est attendue (Polygon)")
        rings = []
        for ring in coords:
            pts = [_point(p) for p in ring]
            if len(pts) >= 2 and pts[0] == pts[-1]:
                pts = pts[:-1]
            # supprime les doublons consécutifs
            pts = [p for i, p in enumerate(pts) if i == 0 or p != pts[i - 1]]
            if len(pts) < 3:
                raise GeometryError("Une surface doit avoir au moins 3 sommets")
            rings.append(pts + [pts[0]])
        n = sum(len(r) for r in rings)
        out = {"type": "Polygon", "coordinates": rings}
    else:
        if t != "LineString" or not isinstance(coords, list):
            raise GeometryError("Une ligne est attendue (LineString)")
        pts = [_point(p) for p in coords]
        pts = [p for i, p in enumerate(pts) if i == 0 or p != pts[i - 1]]
        if len(pts) < 2:
            raise GeometryError("Une ligne doit avoir au moins 2 points")
        n = len(pts)
        out = {"type": "LineString", "coordinates": pts}
    if n > MAX_VERTICES:
        raise GeometryError(f"Trop de sommets ({n} > {MAX_VERTICES})")
    return out


def _to_m(lon, lat, lat0):
    return (math.radians(lon) * R_EARTH * math.cos(math.radians(lat0)), math.radians(lat) * R_EARTH)


def ring_area_m2(ring: list[list[float]]) -> float:
    lat0 = sum(p[1] for p in ring) / len(ring)
    pts = [_to_m(p[0], p[1], lat0) for p in ring]
    s = sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(pts, pts[1:]))
    return abs(s) / 2


def measure(geom: dict) -> dict:
    if geom["type"] == "Polygon":
        outer, *holes = geom["coordinates"]
        return {"area_m2": round(max(0.0, ring_area_m2(outer) - sum(ring_area_m2(h) for h in holes)), 2)}
    pts = geom["coordinates"]
    lat0 = sum(p[1] for p in pts) / len(pts)
    m = [_to_m(p[0], p[1], lat0) for p in pts]
    return {"length_m": round(sum(math.dist(a, b) for a, b in zip(m, m[1:])), 2)}


def point_in_polygon(lon: float, lat: float, geom: dict) -> bool:
    if geom.get("type") != "Polygon":
        return False

    def inside(ring):
        res = False
        for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
            if (y1 > lat) != (y2 > lat) and lon < (x2 - x1) * (lat - y1) / (y2 - y1) + x1:
                res = not res
        return res

    outer, *holes = geom["coordinates"]
    return inside(outer) and not any(inside(h) for h in holes)
