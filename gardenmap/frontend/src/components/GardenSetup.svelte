<script>
  import { api } from '../lib/api.js';
  import { app, guard } from '../lib/store.svelte.js';
  import { parseLatLon } from '../lib/geomap.js';
  import { geolocationAvailable, explainGeoError } from '../lib/gps.js';

  /** onpreview({lat, lon, zoom}) : recentre la carte ; getView() : {lat, lon, zoom} de la carte ; onsaved(garden) */
  let { onpreview, getView, onsaved, oncancel } = $props();

  let q = $state('');
  let results = $state([]);
  let searching = $state(false);
  let error = $state(null);
  let picked = $state(null);
  let timer;

  function onInput() {
    clearTimeout(timer);
    error = null;
    const coords = parseLatLon(q);
    if (coords && /\d/.test(q) && !/[a-z]{3}/i.test(q.replace(/https?:\/\/\S+/, ''))) {
      results = [{ label: `Coordonnées ${coords.lat.toFixed(6)}, ${coords.lon.toFixed(6)}`, ...coords }];
      return;
    }
    if (q.trim().length < 3) { results = []; return; }
    timer = setTimeout(search, 350);
  }

  async function search() {
    searching = true;
    try {
      results = await api.get(`geocode?q=${encodeURIComponent(q.trim())}`);
      if (!results.length) error = 'Aucune adresse trouvée.';
    } catch (e) {
      error = e.message;
    } finally {
      searching = false;
    }
  }

  function choose(r) {
    picked = r;
    results = [];
    q = r.label;
    onpreview?.({ lat: r.lat, lon: r.lon, zoom: 19.5 });
  }

  function useGps() {
    if (!geolocationAvailable()) return (error = explainGeoError(null));
    navigator.geolocation.getCurrentPosition(
      (p) => choose({ label: 'Ma position', lat: p.coords.latitude, lon: p.coords.longitude }),
      (e) => (error = explainGeoError(e)),
      { enableHighAccuracy: true, timeout: 20000 },
    );
  }

  async function save() {
    const v = getView?.() || { ...picked, zoom: 19.5 };
    const r = await guard(() => api.put('garden', { ...v, label: picked?.label || app.meta.garden?.label || '' }), 'Emplacement du jardin enregistré');
    if (r) {
      app.meta.garden = r;
      onsaved?.(r);
    }
  }
</script>

<div class="gs">
  <div class="search">
    <input type="search" placeholder="Adresse du jardin ou coordonnées GPS" bind:value={q} oninput={onInput} autocomplete="street-address" />
    {#if searching}<span class="spin muted small-text">…</span>{/if}
  </div>
  {#if results.length}
    <ul class="res">
      {#each results as r}<li><button onclick={() => choose(r)}>📍 {r.label}</button></li>{/each}
    </ul>
  {/if}
  {#if error}<div class="notice small-text">{error}</div>{/if}
  <div class="row">
    <button class="small" onclick={useGps}>📡 Je suis dans le jardin</button>
  </div>
  <p class="muted small-text">Ajustez ensuite la carte pour cadrer tout le jardin : c'est la vue qui s'affichera à l'ouverture.</p>
  <div class="row">
    <button class="primary grow" disabled={!picked && !getView} onclick={save}>Enregistrer cette vue</button>
    {#if oncancel}<button class="ghost" onclick={() => oncancel()}>Annuler</button>{/if}
  </div>
</div>

<style>
  .gs { display: grid; gap: 10px; }
  .search { position: relative; }
  .spin { position: absolute; right: 12px; top: 12px; }
  .res { list-style: none; margin: 0; padding: 4px; border: 1px solid var(--line); border-radius: 12px; background: var(--surface); max-height: 240px; overflow-y: auto; }
  .res button { width: 100%; justify-content: flex-start; border: 0; font-weight: 500; white-space: normal; text-align: left; border-radius: 8px; }
  .res button:hover { background: var(--leaf-soft); }
</style>
