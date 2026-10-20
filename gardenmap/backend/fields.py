"""Catalogue des attributs d'une espèce : sert au formulaire, à l'IA et à la validation."""

MONTHS = list(range(1, 13))

CATEGORIES = [
    ("arbre", "Arbre"),
    ("fruitier", "Arbre fruitier"),
    ("arbuste", "Arbuste"),
    ("haie", "Haie"),
    ("grimpante", "Grimpante"),
    ("vivace", "Vivace"),
    ("annuelle", "Annuelle"),
    ("bulbe", "Bulbe"),
    ("aromatique", "Aromatique"),
    ("potager", "Potager"),
    ("aquatique", "Aquatique"),
    ("graminee", "Graminée"),
    ("autre", "Autre"),
]

STATUSES = [
    ("en_place", "En place"),
    ("malade", "Malade"),
    ("mort", "Mort"),
    ("arrache", "Arraché"),
    ("deplace", "Déplacé hors du jardin"),
]

ORIGINS = ["Pépinière", "Semis", "Bouture", "Division", "Don", "Déjà présent", "Autre"]
EXPOSURES = ["Soleil", "Mi-ombre", "Ombre"]

# type : text, textarea, number, select, multi, months, bool
SPECIES_FIELDS = [
    # Développement
    {"key": "height_adult_m", "label": "Hauteur adulte", "unit": "m", "type": "number", "section": "Développement"},
    {"key": "spread_adult_m", "label": "Envergure adulte", "unit": "m", "type": "number", "section": "Développement"},
    {"key": "growth_rate", "label": "Croissance", "type": "select", "options": ["Lente", "Moyenne", "Rapide"], "section": "Développement"},
    {"key": "longevity", "label": "Longévité", "type": "text", "section": "Développement"},
    {"key": "foliage", "label": "Feuillage", "type": "select", "options": ["Caduc", "Semi-persistant", "Persistant"], "section": "Développement"},
    # Conditions
    {"key": "exposure", "label": "Exposition", "type": "multi", "options": EXPOSURES, "section": "Conditions"},
    {"key": "soil", "label": "Type de sol", "type": "text", "section": "Conditions"},
    {"key": "ph", "label": "pH", "type": "text", "section": "Conditions"},
    {"key": "drainage", "label": "Drainage", "type": "select", "options": ["Sol drainé", "Indifférent", "Sol frais à humide"], "section": "Conditions"},
    {"key": "water_need", "label": "Besoin en eau", "type": "select", "options": ["Faible", "Moyen", "Élevé"], "section": "Conditions"},
    {"key": "hardiness_c", "label": "Rusticité", "unit": "°C", "type": "number", "section": "Conditions"},
    # Cycle
    {"key": "flowering_months", "label": "Floraison", "type": "months", "section": "Cycle"},
    {"key": "flower_color", "label": "Couleur des fleurs", "type": "text", "section": "Cycle"},
    {"key": "fruiting_months", "label": "Fructification / récolte", "type": "months", "section": "Cycle"},
    {"key": "planting_months", "label": "Période de plantation", "type": "months", "section": "Cycle"},
    # Soins
    {"key": "pruning_months", "label": "Période de taille", "type": "months", "section": "Soins"},
    {"key": "pruning", "label": "Taille", "type": "textarea", "section": "Soins"},
    {"key": "fertilizing", "label": "Fertilisation", "type": "textarea", "section": "Soins"},
    {"key": "mulching", "label": "Paillage", "type": "textarea", "section": "Soins"},
    {"key": "winter_protection", "label": "Protection hivernale", "type": "textarea", "section": "Soins"},
    {"key": "propagation", "label": "Multiplication", "type": "text", "section": "Soins"},
    # Santé
    {"key": "diseases", "label": "Maladies courantes", "type": "textarea", "section": "Santé"},
    {"key": "pests", "label": "Ravageurs courants", "type": "textarea", "section": "Santé"},
    {"key": "treatments", "label": "Traitements recommandés", "type": "textarea", "section": "Santé"},
    # Usages et risques
    {"key": "melliferous", "label": "Mellifère", "type": "bool", "section": "Usages et risques"},
    {"key": "edible", "label": "Comestible", "type": "text", "section": "Usages et risques"},
    {"key": "toxicity", "label": "Toxicité (humains, animaux)", "type": "textarea", "section": "Usages et risques"},
    {"key": "invasive", "label": "Envahissante", "type": "bool", "section": "Usages et risques"},
]

# Champs de premier niveau de l'espèce que l'IA peut aussi proposer
SPECIES_TOP_FIELDS = [
    {"key": "botanical_name", "label": "Nom botanique", "type": "text", "section": "Identité"},
    {"key": "family", "label": "Famille", "type": "text", "section": "Identité"},
    {"key": "category", "label": "Catégorie", "type": "select", "options": [c for c, _ in CATEGORIES], "section": "Identité"},
]

FIELD_BY_KEY = {f["key"]: f for f in SPECIES_FIELDS + SPECIES_TOP_FIELDS}


def clean_value(field: dict, value):
    """Normalise une valeur selon le type du champ ; renvoie None si elle est inutilisable."""
    t = field["type"]
    if value is None or value == "" or value == []:
        return None
    if t == "number":
        try:
            return float(str(value).replace(",", ".").split()[0])
        except (ValueError, IndexError):
            return None
    if t == "bool":
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ("true", "oui", "yes", "1")
    if t == "months":
        if not isinstance(value, list):
            value = [value]
        out = sorted({int(m) for m in value if str(m).isdigit() and 1 <= int(m) <= 12})
        return out or None
    if t == "multi":
        if not isinstance(value, list):
            value = [value]
        opts = field.get("options", [])
        out = [o for o in opts if any(str(v).strip().lower() == o.lower() for v in value)]
        return out or None
    if t == "select":
        opts = field.get("options", [])
        for o in opts:
            if str(value).strip().lower() == o.lower():
                return o
        return None
    return str(value).strip()[:4000] or None


def catalog() -> dict:
    return {
        "species_fields": SPECIES_FIELDS,
        "categories": [{"key": k, "label": l} for k, l in CATEGORIES],
        "statuses": [{"key": k, "label": l} for k, l in STATUSES],
        "origins": ORIGINS,
        "exposures": EXPOSURES,
    }
