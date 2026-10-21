# GardenMap — add-on Home Assistant

Carte du jardin vu de dessus, fiche de chaque plante, photos horodatées, journal d'entretien.
Carte IGN du jardin avec aplats, plantes géolocalisées au GPS du téléphone, fiches, photos, journal, IA (fiches et diagnostic par photo).

## Installation (add-on local)

1. Copier le dossier `gardenmap/` dans le partage `addons` de Home Assistant
   (add-on Samba ou SSH : `/addons/gardenmap/`).
2. **Paramètres → Modules complémentaires → Boutique**, menu ⋮ → **Rechercher des mises à jour**.
   « GardenMap » apparaît dans la section **Modules complémentaires locaux**.
3. **Installer** (la première construction prend quelques minutes sur le Raspberry Pi 5),
   activer **Afficher dans la barre latérale**, puis **Démarrer**.

Variante : pousser ce dossier dans un dépôt GitHub et l'ajouter comme dépôt d'add-ons
(`repository.yaml` est fourni ; adapter l'URL).

## Premiers pas

1. Au premier lancement, **Où est votre jardin ?** : tapez l'adresse (géocodeur IGN) ou touchez
   « Je suis dans le jardin », cadrez la carte puis **Enregistrer cette vue**.
2. **✏️ Dessiner les aplats** : tracez les grandes surfaces (pelouse, massifs, terrasse, bâtiments,
   piscine, potager…) et les lignes (murs, clôtures) sur la photo aérienne. Les points s'accrochent aux
   sommets voisins (rayon fixe de 18 px à l'écran : zoomez pour placer un point librement près d'une
   zone, ou touchez **🧲 Accrochage** pour passer en placement libre). Dessinez d'abord les grandes
   zones, les petites se placent par-dessus.
3. **＋ Plante ici** au pied d'une plante : mesure GPS moyennée, puis ajustement sous la cible.
   La fiche indique automatiquement la zone où se trouve la plante.

## Carte et calques (0.3.0)

Le fond vient directement de l'IGN (Géoplateforme, licence ouverte Etalab 2.0) : photographies
aériennes, Plan IGN, limites cadastrales en option. Les tuiles sont chargées par le navigateur depuis
`data.geopf.fr` ; l'add-on détecte le niveau de zoom le plus fin disponible autour du jardin.
Bouton **🗂️** : *Photo seule*, *Photo + aplats* ou *Plan simplifié* (photo atténuée en gris,
aplats opaques), avec réglage fin des opacités. Ces préférences sont propres à chaque appareil.

**Netteté.** La photo IGN a une résolution d'environ 20 cm par pixel (zoom natif 19) : au-delà,
elle est seulement agrandie. Avec **Fondu au zoom** (activé par défaut), la photo s'estompe quand on
zoome au-delà de sa netteté et les aplats, nets à tous les zooms, prennent le relais.
**Réglages → Autre source de photos aériennes** permet d'ajouter un fond supplémentaire (tuiles XYZ/WMTS
en Web Mercator), avec un test sur le jardin ; vérifiez les conditions d'utilisation de la source.

Plus besoin d'importer ni de caler une image : les plantes et les zones sont enregistrées en
coordonnées GPS (WGS84). L'export contient les aplats en `zones.geojson` (ouvrable dans QGIS).

## GPS dans l'app Home Assistant

La géolocalisation du navigateur exige HTTPS, et la page de l'add-on est affichée dans un cadre.
Si le GPS est refusé :
- bouton **Plein écran** (ouvre la même page dans un onglet, souvent autorisé) ;
- ou **Réglages → Position de secours** : choisir le `device_tracker` de l'app compagnon.

## Configuration de l'IA (onglet Configuration de l'add-on)

| Option | Anthropic | Ollama (API compatible OpenAI) |
| --- | --- | --- |
| `ai_provider` | `anthropic` | `openai` |
| `ai_api_key` | clé API | vide |
| `ai_base_url` | vide | `http://IP_DU_PC:11434/v1` |
| `ai_model` | vide (défaut `claude-sonnet-5-5`) | ex. `qwen2.5:14b` (modèle généraliste, pas `-coder`) |

L'IA ne modifie jamais une fiche : elle propose, vous cochez les champs à garder.
Les valeurs saisies ou déjà validées ne sont jamais reproposées.

### Diagnostic d'un problème par photo (0.2.0)

Dans le journal d'une plante, un **Problème** a un bouton **🔬 Diagnostic IA** (il s'ouvre tout seul
si vous ajoutez un problème avec une photo). Choisissez 1 à 4 photos (vue d'ensemble, gros plans,
revers des feuilles) ou prenez-en une nouvelle. Le modèle reçoit les photos réduites à 1 568 px,
l'espèce, l'âge, l'exposition, la saison, votre description et le journal récent. Il renvoie 1 à
4 hypothèses (maladie, ravageur, carence, cause non parasitaire) avec confiance, comment confirmer
sur place, que faire et prévention. Les traitements proposés se limitent aux produits autorisés
aux particuliers (biocontrôle, faible risque, utilisables en agriculture biologique).
Rien n'est enregistré sans **Enregistrer dans le journal**.

Coût indicatif avec Claude Sonnet : environ 1 600 tokens par photo en entrée et 1 000 à 2 000 en sortie,
soit quelques centimes par diagnostic. Avec Ollama, il faut un modèle qui accepte les images
(ex. `qwen2.5vl`, `llama3.2-vision`).

## Données

`/data/gardenmap.db` (SQLite, dont les aplats en GeoJSON), `/data/photos/<id>/` (original + 2 000 px + miniature). Tout est inclus dans les sauvegardes HA ; **Réglages → Exporter tout** produit un zip.

## Développement

```sh
cd gardenmap
pip install -r backend/requirements.txt pytest
python -m pytest backend/tests                 # tests API, zones, IA simulée
GARDENMAP_DATA=/tmp/gm python -m uvicorn backend.main:app --port 8099
cd frontend && npm install && npm test && npm run dev   # interface sur http://localhost:5173
```

API documentée sur `/api/docs`. Surfaces et longueurs sont calculées côté serveur (`backend/geo.py`)
et côté interface (`frontend/src/lib/geomap.js`) avec la même projection locale.
