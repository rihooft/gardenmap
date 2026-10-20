"""Enrichissement d'une fiche espèce par un modèle de langage.

Le module ne modifie jamais la base : il renvoie des propositions champ par champ,
que l'utilisateur accepte ou refuse dans l'interface.
"""
import json
import re

import httpx

from .fields import FIELD_BY_KEY, SPECIES_FIELDS, SPECIES_TOP_FIELDS, clean_value

DEFAULT_MODELS = {"anthropic": "claude-sonnet-5-5"}
TIMEOUT = httpx.Timeout(120.0, connect=10.0)


class AIError(Exception):
    pass


def _field_doc() -> str:
    lines = []
    for f in SPECIES_TOP_FIELDS + SPECIES_FIELDS:
        t = f["type"]
        if t == "months":
            hint = "liste d'entiers 1-12"
        elif t in ("select", "multi"):
            hint = ("une valeur parmi" if t == "select" else "liste parmi") + " : " + ", ".join(f["options"])
        elif t == "number":
            hint = "nombre" + (f" en {f['unit']}" if f.get("unit") else "")
        elif t == "bool":
            hint = "true ou false"
        else:
            hint = "texte court en français"
        lines.append(f'- "{f["key"]}" ({f["label"]}) : {hint}')
    return "\n".join(lines)


SYSTEM = (
    "Tu es un botaniste et jardinier expérimenté qui conseille un jardinier amateur en France "
    "(climat tempéré, zone de rusticité USDA 8). Tu réponds uniquement par un objet JSON valide, "
    "sans texte autour. N'invente rien : si tu ne connais pas une valeur avec une bonne confiance, "
    "omets la clé. Privilégie les traitements biologiques. Pour la toxicité, mentionne les humains, "
    "les chiens, les chats et les oiseaux de compagnie quand c'est pertinent."
)


def build_prompt(species: dict) -> str:
    known = {
        "nom commun": species.get("common_name"),
        "nom botanique": species.get("botanical_name"),
        "cultivar": species.get("cultivar"),
        "famille": species.get("family"),
    }
    known = {k: v for k, v in known.items() if v}
    return (
        "Plante à documenter : " + json.dumps(known, ensure_ascii=False) + "\n\n"
        "Renvoie un objet JSON avec les clés suivantes (toutes facultatives) :\n"
        + _field_doc()
        + '\n- "confidence" : "haute", "moyenne" ou "faible" pour l\'ensemble de la fiche\n'
        '- "note" : une phrase si l\'identification de la plante est ambiguë'
    )


def extract_json(text: str) -> dict:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if fence:
        text = fence.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise AIError("La réponse de l'IA ne contient pas de JSON.")
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise AIError("JSON invalide renvoyé par l'IA.") from exc



# ---------------------------------------------------------------------------
# Appel aux fournisseurs. Un message = liste de parties {"type": "text", "text"}
# ou {"type": "image", "data": <base64 JPEG>}.
# ---------------------------------------------------------------------------
async def _call_anthropic(opts: dict, system: str, parts: list[dict], max_tokens: int) -> str:
    key = opts.get("ai_api_key")
    if not key:
        raise AIError("Clé d'API Anthropic manquante dans la configuration de l'add-on.")
    base = (opts.get("ai_base_url") or "https://api.anthropic.com").rstrip("/")
    content = [
        {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": p["data"]}}
        if p["type"] == "image" else {"type": "text", "text": p["text"]}
        for p in parts
    ]
    body = {
        "model": opts.get("ai_model") or DEFAULT_MODELS["anthropic"],
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": content}],
    }
    headers = {"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        r = await client.post(f"{base}/v1/messages", json=body, headers=headers)
    if r.status_code >= 400:
        raise AIError(f"Erreur de l'API Anthropic ({r.status_code}) : {r.text[:300]}")
    data = r.json()
    return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")


async def _call_openai(opts: dict, system: str, parts: list[dict], max_tokens: int) -> str:
    base = (opts.get("ai_base_url") or "https://api.openai.com/v1").rstrip("/")
    model = opts.get("ai_model")
    if not model:
        raise AIError("Nom du modèle manquant dans la configuration de l'add-on (ai_model).")
    headers = {"content-type": "application/json"}
    if opts.get("ai_api_key"):
        headers["authorization"] = f"Bearer {opts['ai_api_key']}"
    content = [
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{p['data']}"}}
        if p["type"] == "image" else {"type": "text", "text": p["text"]}
        for p in parts
    ]
    body = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": content}],
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
        "max_tokens": max_tokens,
    }
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        r = await client.post(f"{base}/chat/completions", json=body, headers=headers)
    if r.status_code >= 400:
        raise AIError(f"Erreur de l'API ({r.status_code}) : {r.text[:300]}")
    return r.json()["choices"][0]["message"]["content"]


def provider_call(opts: dict):
    provider = opts.get("ai_provider", "none")
    if provider == "anthropic":
        return _call_anthropic
    if provider == "openai":
        return _call_openai
    raise AIError("Aucun fournisseur d'IA n'est configuré (option ai_provider de l'add-on).")


def source_label(opts: dict) -> str:
    provider = opts.get("ai_provider")
    model = opts.get("ai_model") or DEFAULT_MODELS.get(provider, "")
    return f"IA · {model}" if model else "IA"


# ---------------------------------------------------------------------------
# Fiche espèce
# ---------------------------------------------------------------------------
def normalize_proposals(raw: dict) -> tuple[dict, dict]:
    """Garde les clés connues, normalise les types ; renvoie (propositions, infos)."""
    proposals = {}
    for key, value in raw.items():
        field = FIELD_BY_KEY.get(key)
        if not field:
            continue
        cleaned = clean_value(field, value)
        if cleaned is not None:
            proposals[key] = cleaned
    info = {k: raw.get(k) for k in ("confidence", "note") if raw.get(k)}
    return proposals, info


async def enrich(opts: dict, species: dict, call=None) -> dict:
    call = call or provider_call(opts)
    text = await call(opts, SYSTEM, [{"type": "text", "text": build_prompt(species)}], 3000)
    proposals, info = normalize_proposals(extract_json(text))
    return {"proposals": proposals, "source": source_label(opts), **info}


# ---------------------------------------------------------------------------
# Diagnostic d'un problème à partir de photos
# ---------------------------------------------------------------------------
DIAG_SYSTEM = (
    "Tu es phytopathologiste et jardinier expérimenté. Tu aides un jardinier amateur en France "
    "(climat tempéré) à identifier un problème sur une plante à partir de photos. Tu réponds uniquement "
    "par un objet JSON valide, sans texte autour. Sois honnête sur l'incertitude : une photo ne suffit "
    "souvent pas, donne alors des hypothèses avec une confiance faible et dis comment les départager. "
    "Distingue les maladies, les ravageurs, les carences et les causes non parasitaires (gel, sécheresse, "
    "brûlure, excès d'eau). Réglementation : depuis 2019 en France, les particuliers ne peuvent utiliser "
    "que des produits de biocontrôle, à faible risque ou utilisables en agriculture biologique ; ne propose "
    "jamais d'autre produit. Privilégie d'abord les gestes sans produit (taille, ramassage, arrosage, auxiliaires)."
)

DIAG_TYPES = ["maladie", "ravageur", "carence", "non parasitaire", "autre"]
LEVELS = ["haute", "moyenne", "faible"]
SEASONS = {12: "hiver", 1: "hiver", 2: "hiver", 3: "printemps", 4: "printemps", 5: "printemps",
           6: "été", 7: "été", 8: "été", 9: "automne", 10: "automne", 11: "automne"}


def build_diagnosis_prompt(ctx: dict) -> str:
    sp = ctx.get("species") or {}
    attrs = sp.get("attrs") or {}
    plant = {
        "nom": ctx.get("nickname") or sp.get("common_name"),
        "espèce": sp.get("common_name"),
        "nom botanique": sp.get("botanical_name"),
        "cultivar": sp.get("cultivar"),
        "âge (ans)": ctx.get("age_years"),
        "exposition à cet endroit": ctx.get("exposure"),
        "sol à cet endroit": ctx.get("soil"),
        "zone du jardin": ctx.get("zone"),
        "maladies connues de l'espèce": attrs.get("diseases"),
        "ravageurs connus de l'espèce": attrs.get("pests"),
    }
    plant = {k: v for k, v in plant.items() if v not in (None, "")}
    date = ctx["date"]
    lines = [
        "Plante : " + json.dumps(plant, ensure_ascii=False),
        f"Date de l'observation : {date} ({SEASONS[int(date[5:7])]}).",
    ]
    if ctx.get("description"):
        lines.append("Ce qu'observe le jardinier : " + ctx["description"])
    if ctx.get("history"):
        lines.append("Journal récent de la plante : " + json.dumps(ctx["history"], ensure_ascii=False))
    lines.append(f"{ctx['photo_count']} photo(s) jointe(s).")
    lines.append(
        "\nRenvoie un objet JSON :\n"
        '{\n  "plant_visible": true/false (la plante et le symptôme sont-ils visibles et nets ?),\n'
        '  "symptoms": "description factuelle de ce que tu vois",\n'
        '  "hypotheses": [  // 1 à 4, de la plus probable à la moins probable\n'
        '    {"name": "nom courant (nom scientifique)", "type": "' + " | ".join(DIAG_TYPES) + '",\n'
        '     "confidence": "haute | moyenne | faible",\n'
        '     "evidence": "ce qui, sur la photo ou dans le contexte, va dans ce sens",\n'
        '     "check": "comment confirmer sur place (où regarder, quoi chercher)",\n'
        '     "actions": ["gestes à faire, du plus simple au plus fort, produits autorisés aux particuliers"],\n'
        '     "prevention": "comment éviter que ça revienne"}\n'
        "  ],\n"
        '  "urgency": "faible | moyenne | forte" (risque pour la plante ou de propagation aux voisines),\n'
        '  "advice": "une ou deux phrases de conseil général, ou quoi photographier en plus"\n}'
    )
    return "\n".join(lines)


def _txt(v, limit=1200):
    return str(v).strip()[:limit] if v not in (None, "") else None


def normalize_diagnosis(raw: dict) -> dict:
    hyps = []
    for h in (raw.get("hypotheses") or [])[:4]:
        if not isinstance(h, dict) or not _txt(h.get("name")):
            continue
        typ = str(h.get("type", "")).strip().lower()
        conf = str(h.get("confidence", "")).strip().lower()
        actions = h.get("actions") or []
        if isinstance(actions, str):
            actions = [actions]
        hyps.append({
            "name": _txt(h["name"], 200),
            "type": typ if typ in DIAG_TYPES else "autre",
            "confidence": conf if conf in LEVELS else "faible",
            "evidence": _txt(h.get("evidence")),
            "check": _txt(h.get("check")),
            "actions": [a for a in (_txt(x, 400) for x in actions[:6]) if a],
            "prevention": _txt(h.get("prevention")),
        })
    urgency = str(raw.get("urgency", "")).strip().lower()
    return {
        "plant_visible": bool(raw.get("plant_visible", True)),
        "symptoms": _txt(raw.get("symptoms")),
        "hypotheses": hyps,
        "urgency": urgency if urgency in ("faible", "moyenne", "forte") else None,
        "advice": _txt(raw.get("advice")),
    }


async def diagnose(opts: dict, ctx: dict, images_b64: list[str], call=None) -> dict:
    if not images_b64:
        raise AIError("Il faut au moins une photo pour le diagnostic.")
    call = call or provider_call(opts)
    ctx = {**ctx, "photo_count": len(images_b64)}
    parts = [{"type": "image", "data": d} for d in images_b64]
    parts.append({"type": "text", "text": build_diagnosis_prompt(ctx)})
    text = await call(opts, DIAG_SYSTEM, parts, 2500)
    result = normalize_diagnosis(extract_json(text))
    if not result["hypotheses"] and result["plant_visible"]:
        raise AIError("L'IA n'a proposé aucune hypothèse exploitable.")
    return {**result, "source": source_label(opts)}
