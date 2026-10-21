<script>
  import { app, go, guard } from '../lib/store.svelte.js';
  import { api } from '../lib/api.js';
  import { kindOf, fmtMeasure } from '../lib/geomap.js';

  // --- source de tuiles personnalisée ---
  const cs = app.meta.custom_source;
  let src = $state({ label: cs?.label || '', url: cs?.url || '', native: cs?.native || 19, attribution: cs?.attribution || '' });
  let testTiles = $state(null); // [{ z, url, ok }]

  function tileAt(url, z) {
    const g = app.meta.garden || { lat: 46.6, lon: 2.4 };
    const n = 2 ** z;
    const x = Math.floor(((g.lon + 180) / 360) * n);
    const r = (g.lat * Math.PI) / 180;
    const y = Math.floor(((1 - Math.asinh(Math.tan(r)) / Math.PI) / 2) * n);
    return url.replace('{z}', z).replace('{x}', x).replace('{y}', y);
  }

  function testSource() {
    const n = +src.native || 19;
    testTiles = [n - 1, n, n + 1].map((z) => ({ z, url: tileAt(src.url.trim(), z), ok: null }));
  }

  async function saveSource(clear = false) {
    const body = clear ? { url: '' } : $state.snapshot(src);
    const r = await guard(() => api.put('settings/custom-source', body), clear ? 'Source supprimée' : 'Source enregistrée : choisissez-la dans 🗂️ sur la carte');
    if (!r) return;
    app.meta.custom_source = r.custom_source;
    if (clear) { src = { label: '', url: '', native: 19, attribution: '' }; testTiles = null; }
  }

  // --- appareil Home Assistant ---
  let trackers = $state(null);
  let trackerError = $state(null);
  async function loadTrackers() {
    try { trackers = await api.get('ha/trackers'); } catch (e) { trackerError = e.message; }
  }
  if (app.meta?.ha_api) loadTrackers();

  async function setTracker(entity_id) {
    const r = await guard(() => api.put('settings/tracker', { entity_id }), 'Appareil enregistré');
    if (r) app.meta.tracker_entity = r.tracker_entity;
  }

  // résumé des aplats par type
  let summary = $derived.by(() => {
    const m = new Map();
    for (const z of app.zones) {
      const k = kindOf(app.meta, z.kind);
      const cur = m.get(k.key) || { kind: k, count: 0, area_m2: 0, length_m: 0 };
      cur.count++;
      cur.area_m2 += z.area_m2 || 0;
      cur.length_m += z.length_m || 0;
      m.set(k.key, cur);
    }
    return [...m.values()].sort((a, b) => b.area_m2 - a.area_m2 || b.length_m - a.length_m);
  });
</script>

<div class="page">
  <h1>Réglages</h1>

  <section class="card">
    <h2>Emplacement du jardin</h2>
    {#if app.meta.garden}
      <p class="small-text">{app.meta.garden.label || 'Jardin'} · {app.meta.garden.lat.toFixed(6)}, {app.meta.garden.lon.toFixed(6)}</p>
      <p class="muted small-text">C'est la vue affichée à l'ouverture de la carte.</p>
    {:else}
      <p class="muted small-text">Pas encore défini.</p>
    {/if}
    <button onclick={() => go('/', { situer: 1 })}>{app.meta.garden ? 'Changer la vue de départ' : 'Situer le jardin'}</button>
  </section>

  <section class="card">
    <h2>Autre source de photos aériennes</h2>
    <p class="muted small-text">
      Ajoute un fond de carte en plus de l'IGN, à partir de l'adresse de ses tuiles (format XYZ ou WMTS en
      projection Web Mercator, avec <code>{'{z}'}</code>, <code>{'{x}'}</code>, <code>{'{y}'}</code>).
      Vérifiez que les conditions d'utilisation de la source vous y autorisent.
    </p>
    <div class="grid2">
      <label class="field">Nom <input bind:value={src.label} placeholder="Ma source" /></label>
      <label class="field">Zoom natif maximal <span class="hint">au-delà, l'image est agrandie</span>
        <input type="number" min="10" max="23" bind:value={src.native} />
      </label>
    </div>
    <label class="field">Adresse des tuiles
      <input bind:value={src.url} placeholder={'https://exemple.fr/tuiles/{z}/{x}/{y}.jpg'} autocomplete="off" spellcheck="false" />
    </label>
    <label class="field">Attribution <span class="hint">mention de la source affichée sur la carte</span>
      <input bind:value={src.attribution} placeholder="© Fournisseur" />
    </label>
    <div class="row">
      <button class="small" disabled={!src.url.includes('{z}')} onclick={testSource}>Tester sur le jardin</button>
      <button class="primary small" disabled={!src.url.trim()} onclick={() => saveSource()}>Enregistrer</button>
      {#if app.meta.custom_source}<button class="small danger" onclick={() => saveSource(true)}>Supprimer</button>{/if}
    </div>
    {#if testTiles}
      <div class="tiles">
        {#each testTiles as t}
          <figure>
            <img src={t.url} alt="" onload={() => (t.ok = true)} onerror={() => (t.ok = false)} />
            <figcaption>zoom {t.z} · {t.ok === null ? '…' : t.ok ? 'OK' : 'absente'}</figcaption>
          </figure>
        {/each}
      </div>
      <p class="muted small-text">Comparez les trois tuiles : si celle de droite existe et est plus nette, augmentez le zoom natif ; si celle du milieu est absente ou floue, diminuez-le.</p>
    {/if}
  </section>

  <section class="card">
    <h2>Aplats</h2>
    <p class="muted small-text">Les grandes zones du jardin (pelouse, massifs, bâtiments, piscine…) dessinées sur la photo aérienne. Elles servent de plan simplifié et indiquent dans quelle zone se trouve chaque plante.</p>
    {#if summary.length}
      <table>
        <tbody>
          {#each summary as s}
            <tr>
              <td><span class="sw" style="background:{s.kind.color}" class:line={s.kind.geom === 'line'}></span>{s.kind.label}</td>
              <td class="num">{s.count}</td>
              <td class="num">{s.kind.geom === 'line' ? fmtMeasure({ length_m: s.length_m }) : fmtMeasure({ area_m2: s.area_m2 })}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    {/if}
    <button onclick={() => go('/', { zones: 1 })}>✏️ {app.zones.length ? 'Modifier les aplats' : 'Dessiner les aplats'}</button>
  </section>

  <section class="card">
    <h2>Position de secours : app Home Assistant</h2>
    <p class="muted small-text">Si le navigateur refuse le GPS dans l'app Home Assistant, GardenMap peut lire la position envoyée par l'app compagnon de votre téléphone (moins précise, et mise à jour moins souvent).</p>
    {#if !app.meta?.ha_api}
      <p class="muted small-text">Disponible une fois l'add-on installé dans Home Assistant.</p>
    {:else if trackerError}
      <div class="notice">{trackerError}</div>
    {:else if !trackers}
      <p class="muted small-text">Chargement des appareils…</p>
    {:else}
      <select value={app.meta.tracker_entity || ''} onchange={(e) => setTracker(e.currentTarget.value)}>
        <option value="">— Aucun —</option>
        {#each trackers as t}<option value={t.entity_id}>{t.name} ({t.entity_id})</option>{/each}
      </select>
    {/if}
  </section>

  <section class="card">
    <h2>Enrichissement par IA</h2>
    {#if app.meta?.ai_enabled}
      <p class="pill ok">Activé</p>
      <p class="muted small-text">Fiches espèces complétées par l'IA (validées champ par champ) et diagnostic des problèmes à partir de photos.</p>
    {:else}
      <p class="muted small-text">Désactivé. Dans l'onglet Configuration de l'add-on, choisissez <code>anthropic</code> et collez votre clé d'API (Claude Console), ou <code>openai</code> pour une API compatible comme Ollama.</p>
    {/if}
  </section>

  <section class="card">
    <h2>Sauvegarde</h2>
    <p class="muted small-text">Les données et les photos sont incluses dans les sauvegardes de Home Assistant. Vous pouvez aussi tout télécharger dans une archive (base, photos, aplats en GeoJSON).</p>
    <a class="btn" href="api/export" download>⬇ Exporter tout</a>
  </section>
</div>

<style>
  table { border-collapse: collapse; width: 100%; font-size: 0.9rem; }
  td { padding: 6px 4px; border-bottom: 1px solid var(--line); }
  td.num { text-align: right; white-space: nowrap; color: var(--ink-2); }
  .sw { display: inline-block; width: 14px; height: 14px; border-radius: 4px; margin-right: 8px; vertical-align: -2px; border: 1px solid rgb(0 0 0 / 0.15); }
  .sw.line { height: 4px; vertical-align: 3px; }
  .tiles { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; }
  .tiles figure { margin: 0; }
  .tiles img { width: 100%; aspect-ratio: 1; object-fit: cover; border-radius: 8px; background: var(--surface-2); display: block; }
  .tiles figcaption { font-size: 0.75rem; text-align: center; color: var(--ink-2); }
  code { font-size: 0.85em; background: var(--surface-2); padding: 1px 5px; border-radius: 5px; }
</style>
