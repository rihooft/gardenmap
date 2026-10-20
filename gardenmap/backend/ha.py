"""Lecture des positions remontées par l'app compagnon Home Assistant (repli si le GPS
du navigateur est bloqué dans la vue web)."""
import os

import httpx

CORE_API = os.environ.get("GARDENMAP_HA_API", "http://supervisor/core/api")


def _headers() -> dict:
    token = os.environ.get("SUPERVISOR_TOKEN", "")
    return {"Authorization": f"Bearer {token}"} if token else {}


def _tracker(state: dict) -> dict | None:
    attrs = state.get("attributes", {})
    if "latitude" not in attrs or "longitude" not in attrs:
        return None
    return {
        "entity_id": state["entity_id"],
        "name": attrs.get("friendly_name", state["entity_id"]),
        "lat": attrs["latitude"],
        "lon": attrs["longitude"],
        "accuracy": attrs.get("gps_accuracy"),
        "last_updated": state.get("last_updated"),
    }


async def list_trackers() -> list[dict]:
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"{CORE_API}/states", headers=_headers())
    r.raise_for_status()
    out = []
    for s in r.json():
        if s["entity_id"].split(".")[0] in ("device_tracker", "person"):
            t = _tracker(s)
            if t:
                out.append(t)
    return sorted(out, key=lambda t: t["name"].lower())


async def get_tracker(entity_id: str) -> dict | None:
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"{CORE_API}/states/{entity_id}", headers=_headers())
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return _tracker(r.json())
