<script>
  import { onMount, onDestroy, untrack } from 'svelte';
  import { app, route, go, mapView, refreshSpecimens, refreshZones, guard, toast } from '../lib/store.svelte.js';
  import {
    L, BASES, CADASTRE, FRANCE, MAX_ZOOM, createGeoMap, tileLayer, probeNative, loadPrefs, savePrefs,
    kindOf, zoneStyle, measureGeometry, parseLatLon,
  } from '../lib/geomap.js';
  import { CATEGORY_ICON, STATUS_COLOR, ACTIVE_STATUSES, displayName, fmtMeters } from '../lib/format.js';
  import { api, photoUrl } from '../lib/api.js';
  import { watchLive, explainGeoError, geolocationAvailable } from '../lib/gps.js';
  import GpsMeasure from '../components/GpsMeasure.svelte';
  import GardenSetup from '../components/GardenSetup.svelte';
  import LayersSheet from '../components/LayersSheet.svelte';
  import ZoneSheet from '../components/ZoneSheet.svelte';

  const LABEL_ZOOM = 20; // noms des plantes et regroupement désactivé à partir de ce zoom
  const ZONE_LABEL_ZOOM = 19;

  let el = $state();
  let map, cluster, baseLayer, cadastreLayer, zonesGroup, accuracyCircle, gpsDot, liveMarker, liveCircle, stopLive;
  let ready = $state(false);
  let prefs = $state(loadPrefs());
  let natives = { ortho: BASES.ortho.native, plan: BASES.plan.native, cadastre: CADASTRE.native };

  // affichage
  let filterCat = $state(null);
  let onlyIssues = $state(false);
  let showInactive = $state(false);
  let selected = $state(null);
  let live = $state(false);
  let sheet = $state(app.meta.garden ? null : 'setup'); // setup | layers

  // placement d'une plante : { purpose: 'new'|'move'|'duplicate', id, step: 'choose'|'gps'|'crosshair', gps }
  let placing = $state(null);
  let distFromGps = $state(null);
  let coordInput = $state('');
  let showCoordInput = $state(false);

  // édition des aplats
  let zonesMode = $state(false);
  let drawing = $state(null); // { geom: 'polygon'|'line', vertices }
  let pending = $state(null); // { zone, geom, layer, isNew, measure }
  let shapeEditing = $state(false);
  let zoneLayers = new Map();

  let categories = $derived([...new Set(app.specimens.map((s) => s.category).filter(Boolean))]);
  let visible = $derived(
    app.specimens.filter(
      (s) =>
        s.lat != null &&
        (showInactive || ACTIVE_STATUSES.has(s.status)) &&
        (!filterCat || s.category === filterCat) &&
        (!onlyIssues || s.open_issues > 0),
    ),
  );

  const escapeHtml = (t) => String(t).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);

  // ------------------------------------------------------------------ fonds
  function drawBase() {
    baseLayer?.remove();
    baseLayer = null;
    const def = BASES[prefs.base];
    if (def?.url) {
      baseLayer = tileLayer(def, natives[prefs.base], { opacity: prefs.photoOpacity, className: `gm-base gm-base-${prefs.base}` });
      baseLayer.addTo(map);
    }
    cadastreLayer?.remove();
    cadastreLayer = null;
    if (prefs.cadastre) {
      cadastreLayer = tileLayer(CADASTRE, natives.cadastre, { pane: 'cadastre', opacity: 0.9 });
      cadastreLayer.addTo(map);
    }
    el.classList.toggle('no-base', !baseLayer);
    el.classList.toggle('faded', prefs.photoOpacity <= 0.5);
  }

  async function probeAll(lat, lon) {
    const [o, p, c] = await Promise.all([
      probeNative(BASES.ortho, lat, lon, 'ortho'), probeNative(BASES.plan, lat, lon, 'plan'), probeNative(CADASTRE, lat, lon, 'cadastre'),
    ]);
    const changed = o !== natives.ortho || p !== natives.plan || c !== natives.cadastre;
    natives = { ortho: o, plan: p, cadastre: c };
    if (changed && map) drawBase();
  }

  // ------------------------------------------------------------------ aplats
  function drawZones() {
    if (!map) return;
    zonesGroup?.remove();
    zoneLayers = new Map();
    zonesGroup = L.layerGroup();
    if (prefs.zones || zonesMode) {
      const op = zonesMode ? Math.max(prefs.zonesOpacity, 0.55) : prefs.zonesOpacity;
      const items = app.zones
        .map((z) => ({ z, kind: kindOf(app.meta, z.kind) }))
        .sort((a, b) => (a.kind.geom === b.kind.geom ? (b.z.area_m2 ?? 0) - (a.z.area_m2 ?? 0) : a.kind.geom === 'polygon' ? -1 : 1));
      for (const { z, kind } of items) {
        const gj = L.geoJSON(z.geometry, { style: () => zoneStyle(kind, op), interactive: zonesMode, pmIgnore: !zonesMode });
        const layer = gj.getLayers()[0];
        if (z.name && prefs.labels && kind.geom === 'polygon') {
          layer.bindTooltip(escapeHtml(z.name), { permanent: true, direction: 'center', className: 'gm-zlabel', interactive: false });
        }
        if (zonesMode) layer.on('click', (e) => { if (drawing || shapeEditing) return; L.DomEvent.stop(e); selectZone(z, layer); });
        zoneLayers.set(z.id, layer);
        gj.addTo(zonesGroup);
      }
    }
    zonesGroup.addTo(map);
  }

  // ------------------------------------------------------------------ plantes
  function markerIcon(s) {
    const icon = CATEGORY_ICON[s.category] || '🪴';
    const badge = s.open_issues ? `<span class="badge">!</span>` : '';
    const label = `<span class="gm-label">${escapeHtml(displayName(s))}</span>`;
    const cls = ACTIVE_STATUSES.has(s.status) ? '' : ' inactive';
    return L.divIcon({
      className: '',
      html: `<div class="gm-marker${cls}" style="--status:${STATUS_COLOR[s.status] || 'var(--leaf)'}">${icon}${badge}${label}</div>`,
      iconSize: [38, 38],
      iconAnchor: [19, 19],
    });
  }

  function drawMarkers() {
    if (!cluster) return;
    cluster.clearLayers();
    for (const s of visible) {
      if (placing?.purpose === 'move' && placing.id === s.id) continue;
      const m = L.marker([s.lat, s.lon], { icon: markerIcon(s), title: displayName(s), keyboard: true, pmIgnore: true, pane: 'plants' });
      m.on('click', () => { if (!placing && !zonesMode) selected = s; });
      cluster.addLayer(m);
    }
  }

  $effect(() => {
    visible; placing?.id;
    if (ready) untrack(drawMarkers);
  });

  $effect(() => {
    app.zones; prefs.zones; prefs.zonesOpacity; prefs.labels; zonesMode;
    if (ready) untrack(drawZones);
  });

  function prefsChanged() {
    savePrefs($state.snapshot(prefs));
    drawBase();
    drawZones();
  }

  function updateZoomClasses() {
    const z = map.getZoom();
    el.classList.toggle('labels', z >= LABEL_ZOOM);
    el.classList.toggle('zlabels', z >= ZONE_LABEL_ZOOM);
  }

  onMount(() => {
    const g = app.meta.garden;
    const start = mapView.center ? { lat: mapView.center.lat, lon: mapView.center.lng, zoom: mapView.zoom } : g ? g : FRANCE;
    map = createGeoMap(el, start);
    drawBase();
    cluster = L.markerClusterGroup({
      maxClusterRadius: 40,
      disableClusteringAtZoom: LABEL_ZOOM,
      showCoverageOnHover: false,
      clusterPane: 'plants',
      pmIgnore: true,
      iconCreateFunction: (c) => L.divIcon({ className: '', html: `<div class="gm-cluster">${c.getChildCount()}</div>`, iconSize: [42, 42], iconAnchor: [21, 21] }),
    });
    map.addLayer(cluster);
    map.on('moveend', () => { mapView.center = map.getCenter(); mapView.zoom = map.getZoom(); });
    map.on('zoomend', updateZoomClasses);
    map.on('move', onMove);
    map.on('click', () => { if (!zonesMode) selected = null; });
    map.on('pm:create', onZoneDrawn);
    map.on('pm:drawstart', ({ workingLayer }) => {
      workingLayer.on('pm:vertexadded pm:vertexremoved', () => {
        if (drawing) drawing.vertices = workingLayer.getLatLngs().length;
      });
    });
    updateZoomClasses();
    ready = true;
    drawZones();
    drawMarkers();
    if (g) probeAll(g.lat, g.lon);
    handleQuery();
  });

  onDestroy(() => {
    stopLive?.();
    map?.remove();
  });

  function handleQuery() {
    const q = route.query;
    const find = (id) => app.specimens.find((s) => s.id === +id);
    if (q.centrer) {
      const s = find(q.centrer);
      if (s?.lat != null) {
        map.setView([s.lat, s.lon], Math.max(map.getZoom(), LABEL_ZOOM + 0.5));
        selected = s;
      }
    }
    if (q.deplacer && find(q.deplacer)) startPlacing('move', +q.deplacer);
    if (q.dupliquer && find(q.dupliquer)) startPlacing('duplicate', +q.dupliquer);
    if (q.zones) enterZones();
    if (q.situer) sheet = 'setup';
  }

  function gardenSaved(g) {
    sheet = null;
    probeAll(g.lat, g.lon);
  }

  // ------------------------------------------------------------------ placement d'une plante
  function startPlacing(purpose, id = null) {
    selected = null;
    sheet = null;
    placing = { purpose, id, step: 'choose', gps: null };
    if (purpose !== 'new') {
      const s = app.specimens.find((x) => x.id === id);
      if (s?.lat != null) map.setView([s.lat, s.lon], Math.max(map.getZoom(), LABEL_ZOOM + 0.5));
    }
  }

  function chooseManual() {
    placing.step = 'crosshair';
    placing.gps = null;
    clearGpsLayers();
    if (placing.purpose === 'new') map.setZoom(Math.max(map.getZoom(), LABEL_ZOOM));
  }

  function onGpsResult(r) {
    const ll = L.latLng(r.lat, r.lon);
    const g = app.meta.garden;
    if (g && map.distance(ll, [g.lat, g.lon]) > 1000) {
      toast(`Vous êtes à ${(map.distance(ll, [g.lat, g.lon]) / 1000).toFixed(1).replace('.', ',')} km du jardin : placez la plante à la main.`, 'error');
      chooseManual();
      return;
    }
    placing.gps = r;
    placing.step = 'crosshair';
    clearGpsLayers();
    accuracyCircle = L.circle(ll, { radius: r.accuracy, color: '#2a7de1', weight: 2, fillOpacity: 0.12, interactive: false, pmIgnore: true }).addTo(map);
    gpsDot = L.circleMarker(ll, { radius: 5, color: '#fff', weight: 2, fillColor: '#2a7de1', fillOpacity: 1, interactive: false, pmIgnore: true }).addTo(map);
    const z = map.getBoundsZoom(accuracyCircle.getBounds().pad(1.2));
    map.setView(ll, Math.min(Math.max(z, LABEL_ZOOM), MAX_ZOOM));
  }

  function clearGpsLayers() {
    accuracyCircle?.remove();
    gpsDot?.remove();
    accuracyCircle = gpsDot = null;
    distFromGps = null;
  }

  function onMove() {
    if (placing?.step === 'crosshair' && placing.gps) distFromGps = map.distance(map.getCenter(), [placing.gps.lat, placing.gps.lon]);
  }

  function applyCoords() {
    const p = parseLatLon(coordInput);
    if (!p) return toast('Coordonnées non reconnues (ex. 48.8350, 2.5200)', 'error');
    showCoordInput = false;
    onGpsResult({ ...p, accuracy: 1, source: 'coords' });
  }

  function cancelPlacing() {
    clearGpsLayers();
    placing = null;
    showCoordInput = false;
    if (route.query.deplacer || route.query.dupliquer) go('/');
  }

  async function confirmPlacing() {
    const c = map.getCenter();
    const moved = placing.gps ? (distFromGps ?? 0) > 0.05 : true;
    const source = placing.gps ? (moved ? `${placing.gps.source}+ajusté` : placing.gps.source) : 'manual';
    const pos = { lat: +c.lat.toFixed(8), lon: +c.lng.toFixed(8), gps_accuracy: placing.gps && !moved ? placing.gps.accuracy : null, position_source: source };
    const { purpose, id } = placing;
    clearGpsLayers();
    placing = null;
    if (purpose === 'new') {
      go('/nouvelle', { lat: pos.lat, lon: pos.lon, acc: pos.gps_accuracy, src: pos.position_source });
    } else if (purpose === 'move') {
      const r = await guard(() => api.put(`specimens/${id}`, { ...pos, move_reason: 'déplacement' }), 'Position enregistrée');
      if (r) { await refreshSpecimens(); go(`/plante/${id}`); }
    } else {
      const r = await guard(() => api.post(`specimens/${id}/duplicate`, pos), 'Copie créée');
      if (r) { await refreshSpecimens(); go(`/plante/${r.id}/modifier`); }
    }
  }

  // ------------------------------------------------------------------ ma position
  function toggleLive() {
    if (live) {
      stopLive?.();
      liveMarker?.remove(); liveCircle?.remove();
      liveMarker = liveCircle = null;
      live = false;
      return;
    }
    if (!geolocationAvailable()) return toast(explainGeoError(null), 'error');
    live = true;
    let first = true;
    stopLive = watchLive(
      (p) => {
        const ll = L.latLng(p.lat, p.lon);
        if (!liveMarker) {
          liveCircle = L.circle(ll, { radius: p.accuracy, color: '#2a7de1', weight: 1, fillOpacity: 0.1, interactive: false, pmIgnore: true }).addTo(map);
          liveMarker = L.marker(ll, { icon: L.divIcon({ className: '', html: '<div class="gm-me"></div>', iconSize: [18, 18], iconAnchor: [9, 9] }), interactive: false, pmIgnore: true }).addTo(map);
        } else {
          liveMarker.setLatLng(ll);
          liveCircle.setLatLng(ll).setRadius(p.accuracy);
        }
        if (first) { map.panTo(ll); first = false; }
      },
      (err) => { toast(explainGeoError(err), 'error'); toggleLive(); },
    );
  }

  // ------------------------------------------------------------------ édition des aplats
  function enterZones() {
    selected = null;
    sheet = null;
    zonesMode = true;
    if (map.getZoom() < 18.5) map.setZoom(19);
  }

  function exitZones() {
    cancelDrawing();
    discardPending();
    zonesMode = false;
    if (route.query.zones) go('/');
  }

  function startDrawing(geom) {
    discardPending();
    drawing = { geom, vertices: 0 };
    map.pm.enableDraw(geom === 'line' ? 'Line' : 'Polygon', { snappable: true, snapDistance: 18, finishOn: null, continueDrawing: false });
  }

  function drawHandler() {
    return drawing?.geom === 'line' ? map.pm.Draw.Line : map.pm.Draw.Polygon;
  }

  function undoVertex() {
    drawHandler()._removeLastVertex();
    drawing.vertices = Math.max(0, drawing.vertices - 1);
  }

  function finishDrawing() {
    drawHandler()._finishShape();
  }

  function cancelDrawing() {
    if (drawing) map.pm.disableDraw();
    drawing = null;
  }

  function onZoneDrawn(e) {
    const geom = drawing?.geom || (e.shape === 'Line' ? 'line' : 'polygon');
    drawing = null;
    const layer = e.layer;
    layer.setStyle({ color: '#c0392b', weight: 3, fillColor: '#ffffff', fillOpacity: 0.35, dashArray: '6 4' });
    const geometry = layer.toGeoJSON().geometry;
    pending = { zone: {}, geom, layer, isNew: true, measure: measureGeometry(geometry) };
  }

  function selectZone(z, layer) {
    if (drawing) return;
    discardPending();
    const kind = kindOf(app.meta, z.kind);
    pending = { zone: z, geom: kind.geom, layer, isNew: false, measure: z.area_m2 != null ? { area_m2: z.area_m2 } : { length_m: z.length_m } };
    layer.setStyle({ color: '#c0392b', weight: 3, opacity: 1 });
    layer.bringToFront();
  }

  function toggleShape() {
    if (!pending) return;
    if (shapeEditing) {
      pending.layer.pm.disable();
      shapeEditing = false;
      pending.measure = measureGeometry(pending.layer.toGeoJSON().geometry);
      return;
    }
    pending.layer.pm.enable({ snappable: true, snapDistance: 18, allowSelfIntersection: false, removeVertexOn: 'click' });
    pending.layer.on('pm:edit', () => (pending.measure = measureGeometry(pending.layer.toGeoJSON().geometry)));
    shapeEditing = true;
  }

  function discardPending() {
    if (!pending) return;
    pending.layer.pm?.disable();
    if (pending.isNew) pending.layer.remove();
    pending = null;
    shapeEditing = false;
    drawZones(); // rétablit le style et la forme d'origine
  }

  async function savePending(values) {
    const p = pending;
    p.layer.pm?.disable();
    const geometry = p.layer.toGeoJSON().geometry;
    const r = p.isNew
      ? await guard(() => api.post('zones', { ...values, geometry }), 'Zone ajoutée')
      : await guard(() => api.put(`zones/${p.zone.id}`, { ...values, geometry }), 'Zone enregistrée');
    if (!r) return;
    if (p.isNew) p.layer.remove();
    pending = null;
    shapeEditing = false;
    await refreshZones();
  }

  async function deletePending() {
    const z = pending.zone;
    if (!confirm(`Supprimer la zone « ${z.name || kindOf(app.meta, z.kind).label} » ?`)) return;
    const r = await guard(() => api.del(`zones/${z.id}`), 'Zone supprimée');
    if (r === undefined) return;
    pending = null;
    shapeEditing = false;
    await refreshZones();
  }

  const purposeLabel = { new: 'Nouvelle plante', move: 'Déplacer', duplicate: 'Copie à placer' };
  let minVertices = $derived(drawing?.geom === 'line' ? 2 : 3);
</script>

<div class="wrap" class:zones-mode={zonesMode} class:drawing={!!drawing || shapeEditing}>
  <div class="map" bind:this={el}></div>

  {#if zonesMode}
    <div class="topbar">
      <strong class="grow">Aplats du jardin</strong>
      {#if !drawing && !pending}
        <button class="small" onclick={() => startDrawing('polygon')}>＋ Surface</button>
        <button class="small" onclick={() => startDrawing('line')}>＋ Ligne</button>
      {/if}
      <button class="small primary" onclick={exitZones}>Terminé</button>
    </div>
    {#if !drawing && !pending}
      <div class="hint">{app.zones.length ? 'Touchez une zone pour la modifier, ou ajoutez une surface ou une ligne.' : 'Commencez par les grandes surfaces (pelouse), puis dessinez les massifs, la terrasse ou la piscine par-dessus.'}</div>
    {/if}
  {:else if !placing && sheet !== 'setup'}
    <div class="filters">
      <div class="chips">
        <button class="chip" class:on={!filterCat && !onlyIssues} onclick={() => { filterCat = null; onlyIssues = false; }}>Tout ({app.specimens.filter((s) => ACTIVE_STATUSES.has(s.status)).length})</button>
        <button class="chip" class:on={onlyIssues} onclick={() => (onlyIssues = !onlyIssues)}>⚠️ Problèmes</button>
        {#each categories as c}
          <button class="chip" class:on={filterCat === c} onclick={() => (filterCat = filterCat === c ? null : c)}>
            {CATEGORY_ICON[c] || '🪴'} {app.meta.categories.find((x) => x.key === c)?.label || c}
          </button>
        {/each}
        <button class="chip" class:on={showInactive} onclick={() => (showInactive = !showInactive)}>Archivées</button>
      </div>
    </div>
    <div class="side">
      <button class="icon square" title="Affichage" aria-label="Affichage de la carte" onclick={() => (sheet = sheet === 'layers' ? null : 'layers')}>🗂️</button>
      <button class="icon square" title="Dessiner les aplats" aria-label="Dessiner les aplats" onclick={enterZones}>✏️</button>
      <button class="icon square" class:active={live} title="Ma position" aria-label="Afficher ma position" onclick={toggleLive}>📍</button>
    </div>
    {#if !sheet}
      <div class="fabs">
        <button class="primary fab" onclick={() => startPlacing('new')}>＋ Plante ici</button>
      </div>
    {/if}
  {/if}

  {#if selected && !placing && !zonesMode}
    <button class="peek" onclick={() => go(`/plante/${selected.id}`)}>
      {#if selected.cover_photo_id}
        <img src={photoUrl(selected.cover_photo_id, 'th')} alt="" />
      {:else}
        <span class="ph">{CATEGORY_ICON[selected.category] || '🪴'}</span>
      {/if}
      <span class="txt">
        <strong>{displayName(selected)}</strong>
        {#if selected.botanical_name}<em class="muted">{selected.botanical_name}</em>{/if}
        {#if selected.open_issues}<span class="pill warn">{selected.open_issues} problème{selected.open_issues > 1 ? 's' : ''} ouvert{selected.open_issues > 1 ? 's' : ''}</span>{/if}
      </span>
      <span class="go">Fiche ›</span>
    </button>
  {/if}

  {#if placing?.step === 'crosshair'}
    <div class="crosshair" aria-hidden="true"><span></span></div>
  {/if}

  {#if sheet === 'setup'}
    <div class="sheet">
      <h2>Où est votre jardin ?</h2>
      <GardenSetup onpreview={(v) => map.setView([v.lat, v.lon], v.zoom)}
        getView={app.meta.garden || mapView.center ? () => ({ lat: map.getCenter().lat, lon: map.getCenter().lng, zoom: map.getZoom() }) : null}
        onsaved={gardenSaved} oncancel={app.meta.garden ? () => (sheet = null) : null} />
    </div>
  {:else if sheet === 'layers'}
    <LayersSheet {prefs} onchange={prefsChanged} onclose={() => (sheet = null)} />
  {/if}

  {#if drawing}
    <div class="sheet">
      <h2>{drawing.geom === 'line' ? 'Tracer une ligne' : 'Dessiner une surface'}</h2>
      <p class="muted small-text">
        Touchez la carte à chaque angle{drawing.geom === 'polygon' ? ', puis le premier point ou « Terminer » pour fermer la forme' : ', puis « Terminer »'}.
        Les points s'accrochent aux sommets des zones voisines.
      </p>
      <div class="row">
        <button class="primary grow" disabled={drawing.vertices < minVertices} onclick={finishDrawing}>Terminer ({drawing.vertices} point{drawing.vertices > 1 ? 's' : ''})</button>
        <button class="small" disabled={!drawing.vertices} onclick={undoVertex}>↶ Point</button>
        <button class="ghost small" onclick={cancelDrawing}>Abandonner</button>
      </div>
    </div>
  {:else if pending}
    {#key pending.zone.id ?? 'new'}
      <ZoneSheet zone={pending.zone} geom={pending.geom} measure={pending.measure} {shapeEditing}
        onsave={savePending} oncancel={discardPending} ondelete={pending.isNew ? null : deletePending} onshape={pending.isNew ? null : toggleShape} />
    {/key}
  {/if}

  {#if placing?.step === 'choose'}
    <div class="sheet">
      <h2>{purposeLabel[placing.purpose]} — position</h2>
      <button class="primary" onclick={() => (placing.step = 'gps')}>📡 Utiliser le GPS du téléphone</button>
      <button onclick={chooseManual}>✋ Placer à la main sur la carte</button>
      <button class="ghost" onclick={cancelPlacing}>Annuler</button>
    </div>
  {:else if placing?.step === 'gps'}
    <GpsMeasure title="Position de la plante" onresult={onGpsResult} onmanual={chooseManual} oncancel={cancelPlacing} />
  {:else if placing?.step === 'crosshair'}
    <div class="sheet">
      <div class="row">
        <h2 class="grow">{purposeLabel[placing.purpose]}</h2>
        {#if placing.gps}<span class="pill">GPS ±{fmtMeters(placing.gps.accuracy)}</span>{/if}
      </div>
      <p class="muted small-text">
        Déplacez la carte pour amener la cible exactement sur la plante.
        {#if distFromGps != null && distFromGps > 0.05}Décalage par rapport au GPS : {fmtMeters(distFromGps)}.{/if}
      </p>
      {#if showCoordInput}
        <div class="row">
          <input class="grow" placeholder="48.8350, 2.5200 ou lien Google Maps" bind:value={coordInput} onkeydown={(e) => e.key === 'Enter' && applyCoords()} />
          <button onclick={applyCoords}>OK</button>
        </div>
      {/if}
      <div class="row">
        <button class="primary grow" onclick={confirmPlacing}>Valider ici</button>
        {#if !showCoordInput}<button class="small" onclick={() => (showCoordInput = true)}>Coordonnées…</button>{/if}
        <button class="ghost small" onclick={cancelPlacing}>Annuler</button>
      </div>
    </div>
  {/if}
</div>

<style>
  .wrap { position: absolute; inset: 0; }
  .map { position: absolute; inset: 0; }
  .map:global(.no-base) { background: #f1efe6; }
  .map:global(.faded) { background: #f4f2ea; }
  .map:global(.faded) :global(.gm-base) { filter: grayscale(1) contrast(0.85) brightness(1.1); }
  .map :global(.gm-label) { display: none; }
  .map:global(.labels) :global(.gm-label) { display: block; }
  .map :global(.gm-zlabel) { display: none; }
  .map:global(.zlabels) :global(.gm-zlabel) { display: block; }
  .zones-mode .map :global(.leaflet-plants-pane) { opacity: 0.35; }
  /* pendant un tracé, les zones existantes ne doivent pas capter les touchers (l'accrochage reste actif) */
  .drawing .map :global(.leaflet-zones-pane path), .drawing .map :global(.leaflet-zoneLines-pane path) { pointer-events: none !important; }
  .zones-mode .map :global(.leaflet-plants-pane *) { pointer-events: none !important; }

  .filters { position: absolute; top: 10px; left: 10px; right: 64px; z-index: 900; }
  .filters .chip { box-shadow: 0 2px 8px rgb(0 0 0 / 0.15); }
  .side { position: absolute; top: 104px; right: 10px; z-index: 900; display: grid; gap: 8px; }
  .square { width: 44px; height: 44px; min-height: 44px; border-radius: 10px; box-shadow: 0 2px 8px rgb(0 0 0 / 0.2); font-size: 1.15rem; }
  .square.active { background: #2a7de1; border-color: #2a7de1; }
  .fabs { position: absolute; right: 14px; bottom: 26px; z-index: 900; }
  .fab { min-height: 56px; padding: 0 22px; font-size: 1.05rem; box-shadow: var(--shadow); }
  .topbar {
    position: absolute; top: 10px; left: 10px; right: 64px; z-index: 950; display: flex; gap: 8px; align-items: center; flex-wrap: wrap;
    background: var(--surface); border-radius: 14px; padding: 8px 8px 8px 14px; box-shadow: var(--shadow);
  }
  .hint {
    position: absolute; left: 12px; right: 12px; bottom: 16px; z-index: 900; max-width: 520px; margin: 0 auto;
    background: color-mix(in srgb, var(--surface) 92%, transparent); border-radius: 12px; padding: 10px 14px; font-size: 0.9rem; box-shadow: var(--shadow);
  }
  .peek {
    position: absolute; left: 12px; right: 12px; bottom: 96px; z-index: 950; max-width: 520px; margin: 0 auto;
    display: flex; align-items: center; gap: 12px; text-align: left; padding: 10px; min-height: 76px;
    border-radius: 16px; box-shadow: var(--shadow); white-space: normal; font-weight: 400;
  }
  .peek img, .peek .ph { width: 56px; height: 56px; border-radius: 10px; object-fit: cover; flex: none; display: grid; place-items: center; background: var(--surface-2); font-size: 28px; }
  .peek .txt { display: grid; gap: 2px; flex: 1; justify-items: start; }
  .peek .go { color: var(--leaf); font-weight: 700; }
  .crosshair { position: absolute; inset: 0; pointer-events: none; z-index: 800; display: grid; place-items: center; }
  .crosshair span { width: 64px; height: 64px; position: relative; }
  .crosshair span::before, .crosshair span::after { content: ''; position: absolute; background: var(--danger); box-shadow: 0 0 0 1.5px #fff; }
  .crosshair span::before { left: 31px; top: 0; width: 2px; height: 64px; }
  .crosshair span::after { top: 31px; left: 0; height: 2px; width: 64px; }
  .sheet {
    position: absolute; left: 12px; right: 12px; bottom: 12px; z-index: 1000; max-width: 520px; margin: 0 auto;
    background: var(--surface); border-radius: 18px; box-shadow: var(--shadow); padding: 18px; display: grid; gap: 10px;
    max-height: calc(100% - 24px); overflow-y: auto;
  }
</style>
