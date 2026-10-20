// Carte géographique (EPSG:3857) sur les fonds IGN de la Géoplateforme, avec la couche des aplats.
import L from './leaflet-global.js';
import 'leaflet/dist/leaflet.css';
import 'leaflet.markercluster';
import 'leaflet.markercluster/dist/MarkerCluster.css';
import '@geoman-io/leaflet-geoman-free';
import '@geoman-io/leaflet-geoman-free/dist/leaflet-geoman.css';

export { L };

// Leaflet laisse des interstices d'un pixel entre les tuiles aux zooms fractionnaires (le conteneur
// est mis à l'échelle jusqu'à 0,5) : on agrandit chaque tuile de 2 px pour couvrir au moins 1 px à l'écran.
const initTile = L.GridLayer.prototype._initTile;
L.GridLayer.include({
  _initTile(tile) {
    initTile.call(this, tile);
    const size = this.getTileSize();
    tile.style.width = `${size.x + 2}px`;
    tile.style.height = `${size.y + 2}px`;
  },
});

const WMTS = 'https://data.geopf.fr/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&TILEMATRIXSET=PM&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}';
const ATTRIB = '© <a href="https://www.ign.fr/" target="_blank" rel="noopener">IGN</a> – Géoplateforme';

export const BASES = {
  ortho: { label: 'Photo aérienne', url: `${WMTS}&LAYER=ORTHOIMAGERY.ORTHOPHOTOS&STYLE=normal&FORMAT=image/jpeg`, native: 19, probe: [21, 20] },
  plan: { label: 'Plan IGN', url: `${WMTS}&LAYER=GEOGRAPHICALGRIDSYSTEMS.PLANIGNV2&STYLE=normal&FORMAT=image/png`, native: 18, probe: [19] },
  none: { label: 'Aucun fond', url: null },
};
export const CADASTRE = {
  url: `${WMTS}&LAYER=CADASTRALPARCELS.PARCELLAIRE_EXPRESS&STYLE=PCI%20vecteur&FORMAT=image/png`,
  native: 19,
  probe: [20],
};

export const MAX_ZOOM = 22;
export const FRANCE = { lat: 46.6, lon: 2.4, zoom: 6 };

// ---------------------------------------------------------------- préférences d'affichage (par appareil)
const PREFS_KEY = 'gm.mapprefs';
export const PRESETS = {
  photo: { base: 'ortho', photoOpacity: 1, zones: false, zonesOpacity: 0.6 },
  mixte: { base: 'ortho', photoOpacity: 1, zones: true, zonesOpacity: 0.55 },
  plan: { base: 'ortho', photoOpacity: 0.3, zones: true, zonesOpacity: 0.95 },
};
const DEFAULT_PREFS = { ...PRESETS.mixte, cadastre: false, labels: true, preset: 'mixte' };

export function loadPrefs() {
  try {
    return { ...DEFAULT_PREFS, ...JSON.parse(localStorage.getItem(PREFS_KEY) || '{}') };
  } catch {
    return { ...DEFAULT_PREFS };
  }
}

export function savePrefs(p) {
  try {
    localStorage.setItem(PREFS_KEY, JSON.stringify(p));
  } catch {
    /* navigation privée : préférences non conservées */
  }
}

// ---------------------------------------------------------------- zoom natif maximal des tuiles
function tileUrl(tpl, z, lat, lon) {
  const n = 2 ** z;
  const x = Math.floor(((lon + 180) / 360) * n);
  const r = (lat * Math.PI) / 180;
  const y = Math.floor(((1 - Math.asinh(Math.tan(r)) / Math.PI) / 2) * n);
  return tpl.replace('{z}', z).replace('{x}', x).replace('{y}', y);
}

function loads(url) {
  return new Promise((resolve) => {
    const img = new Image();
    const t = setTimeout(() => resolve(false), 8000);
    img.onload = () => { clearTimeout(t); resolve(img.naturalWidth > 0); };
    img.onerror = () => { clearTimeout(t); resolve(false); };
    img.src = url;
  });
}

/** Niveau de zoom le plus fin réellement disponible autour du jardin (mis en cache sur l'appareil). */
export async function probeNative(def, lat, lon, cacheKey) {
  const key = `gm.native.${cacheKey}.${lat.toFixed(3)},${lon.toFixed(3)}`;
  try {
    const cached = localStorage.getItem(key);
    if (cached) return +cached;
  } catch { /* ignore */ }
  let best = def.native;
  for (const z of def.probe) {
    if (z > best && (await loads(tileUrl(def.url, z, lat, lon)))) { best = z; break; }
  }
  try { localStorage.setItem(key, String(best)); } catch { /* ignore */ }
  return best;
}

// ---------------------------------------------------------------- carte
export function createGeoMap(el, center) {
  const map = L.map(el, {
    maxZoom: MAX_ZOOM,
    zoomSnap: 0.25,
    zoomDelta: 0.5,
    wheelPxPerZoomLevel: 90,
    zoomControl: false,
    attributionControl: true,
  });
  map.attributionControl.setPrefix(false);
  map.createPane('zones').style.zIndex = 350;
  map.createPane('zoneLines').style.zIndex = 360;
  map.createPane('cadastre').style.zIndex = 370;
  map.createPane('plants').style.zIndex = 620; // au-dessus des aplats ; inertes pendant l'édition des zones
  map.setView([center.lat, center.lon], center.zoom ?? 19);
  L.control.zoom({ position: 'topright', zoomInTitle: 'Zoomer', zoomOutTitle: 'Dézoomer' }).addTo(map);
  L.control.scale({ position: 'bottomleft', imperial: false, maxWidth: 120 }).addTo(map);
  map.pm.setLang('fr');
  map.pm.setGlobalOptions({ snappable: true, snapDistance: 18, allowSelfIntersection: false, templineStyle: { color: '#c0392b' }, hintlineStyle: { color: '#c0392b', dashArray: '5 5' } });
  const ro = new ResizeObserver(() => map.invalidateSize());
  ro.observe(el);
  map.on('unload', () => ro.disconnect());
  return map;
}

export function tileLayer(def, native, opts = {}) {
  return L.tileLayer(def.url, {
    maxNativeZoom: native,
    maxZoom: MAX_ZOOM,
    attribution: ATTRIB,
    crossOrigin: false,
    pmIgnore: true,
    ...opts,
  });
}

// ---------------------------------------------------------------- aplats
export function kindOf(meta, key) {
  return meta.zone_kinds.find((k) => k.key === key) || { key, label: key, color: '#cccccc', geom: 'polygon' };
}

function darker(hex, f = 0.7) {
  const n = parseInt(hex.slice(1), 16);
  const c = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((v) => Math.round(v * f));
  return `rgb(${c.join(',')})`;
}

export function zoneStyle(kind, opacity, selected = false) {
  if (kind.geom === 'line') {
    return {
      pane: 'zoneLines',
      color: selected ? '#c0392b' : kind.color,
      weight: kind.key === 'mur' ? 5 : 3,
      opacity: Math.max(0.6, opacity),
      dashArray: kind.key === 'cloture' ? '6 5' : null,
      lineCap: 'butt',
    };
  }
  return {
    pane: 'zones',
    fillColor: kind.color,
    fillOpacity: opacity,
    color: selected ? '#c0392b' : darker(kind.color),
    weight: selected ? 3 : 1,
    opacity: selected ? 1 : Math.min(1, opacity + 0.15),
  };
}

/** Surface (m²) ou longueur (m) d'une géométrie GeoJSON, sur une projection locale. */
export function measureGeometry(g) {
  const R = 6371008.8;
  const toM = (lon, lat, lat0) => [((lon * Math.PI) / 180) * R * Math.cos((lat0 * Math.PI) / 180), ((lat * Math.PI) / 180) * R];
  if (g.type === 'Polygon') {
    const ring = g.coordinates[0];
    const lat0 = ring.reduce((s, p) => s + p[1], 0) / ring.length;
    const m = ring.map(([lon, lat]) => toM(lon, lat, lat0));
    let s = 0;
    for (let i = 0; i < m.length - 1; i++) s += m[i][0] * m[i + 1][1] - m[i + 1][0] * m[i][1];
    return { area_m2: Math.abs(s) / 2 };
  }
  const pts = g.coordinates;
  const lat0 = pts.reduce((s, p) => s + p[1], 0) / pts.length;
  const m = pts.map(([lon, lat]) => toM(lon, lat, lat0));
  let len = 0;
  for (let i = 0; i < m.length - 1; i++) len += Math.hypot(m[i + 1][0] - m[i][0], m[i + 1][1] - m[i][1]);
  return { length_m: len };
}

export function fmtMeasure(m) {
  if (m.area_m2 != null) return m.area_m2 >= 10000 ? `${(m.area_m2 / 10000).toFixed(2).replace('.', ',')} ha` : `${Math.round(m.area_m2)} m²`;
  if (m.length_m != null) return `${m.length_m.toFixed(1).replace('.', ',')} m`;
  return '';
}

/** Analyse « 48.8350, 2.5200 », « 48,8350 2,5200 » ou un lien Google Maps (…@48.83,2.52,…). */
export function parseLatLon(text) {
  if (!text) return null;
  const at = text.match(/@(-?\d+\.\d+),(-?\d+\.\d+)/);
  if (at) return { lat: +at[1], lon: +at[2] };
  const nums = text.replace(/(\d),(\d)/g, '$1.$2').match(/-?\d+(?:\.\d+)?/g);
  if (!nums || nums.length < 2) return null;
  const lat = +nums[0], lon = +nums[1];
  if (Math.abs(lat) > 90 || Math.abs(lon) > 180) return null;
  return { lat, lon };
}
