// État partagé de l'application (runes Svelte 5).
import { api } from './api.js';

export const app = $state({
  meta: null,
  zones: [],
  specimens: [],
  species: [],
  loading: true,
  error: null,
  toast: null,
});

export async function loadAll() {
  try {
    const [meta, specimens, species, zones] = await Promise.all([
      api.get('meta'), api.get('specimens'), api.get('species'), api.get('zones'),
    ]);
    Object.assign(app, { meta, specimens, species, zones, loading: false, error: null });
  } catch (e) {
    app.error = e.message;
    app.loading = false;
  }
}

export async function refreshSpecimens() {
  app.specimens = await api.get('specimens');
}

export async function refreshSpecies() {
  app.species = await api.get('species');
}

export async function refreshZones() {
  app.zones = await api.get('zones');
}

let toastTimer;
export function toast(message, kind = 'ok') {
  app.toast = { message, kind };
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (app.toast = null), kind === 'error' ? 6000 : 3000);
}

/** Exécute une action asynchrone et affiche l'erreur éventuelle. */
export async function guard(fn, okMessage) {
  try {
    const r = await fn();
    if (okMessage) toast(okMessage);
    return r;
  } catch (e) {
    toast(e.message, 'error');
    return undefined;
  }
}

// --- routage par fragment d'URL (#/plante/12) -----------------------------
export const route = $state({ path: '/', query: {} });

function parseHash() {
  const raw = location.hash.replace(/^#/, '') || '/';
  const [path, qs] = raw.split('?');
  route.path = path;
  route.query = Object.fromEntries(new URLSearchParams(qs || ''));
}
window.addEventListener('hashchange', parseHash);
parseHash();

export function go(path, query) {
  const qs = query ? '?' + new URLSearchParams(Object.entries(query).filter(([, v]) => v != null && v !== '')) : '';
  location.hash = `#${path}${qs}`;
}

// État de la carte conservé entre les vues
export const mapView = { center: null, zoom: null };
