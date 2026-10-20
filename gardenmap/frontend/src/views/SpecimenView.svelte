<script>
  import { app, go, guard, refreshSpecimens, route } from '../lib/store.svelte.js';
  import { api, photoUrl, uploadPhotos } from '../lib/api.js';
  import { ageYears, fmtAge, fmtDate, fmtMonths, fmtMeters, CATEGORY_ICON, displayName, ACTIVE_STATUSES } from '../lib/format.js';
  import PhotoTimeline from '../components/PhotoTimeline.svelte';
  import Journal from '../components/Journal.svelte';
  import { kindOf } from '../lib/geomap.js';

  let { id } = $props();
  let s = $state(null);
  let notFound = $state(false);
  let uploading = $state(false);

  async function load() {
    try {
      s = await api.get(`specimens/${id}`);
    } catch {
      notFound = true;
    }
  }
  load();

  async function reload() {
    await load();
    await refreshSpecimens();
  }

  async function addPhotos(e) {
    const files = [...(e.currentTarget.files || [])];
    e.currentTarget.value = '';
    if (!files.length) return;
    uploading = true;
    const r = await guard(() => uploadPhotos(id, files));
    uploading = false;
    if (r) {
      const n = r.photos.length;
      if (r.errors.length) alert(r.errors.join('\n'));
      if (n) await reload();
    }
  }

  async function remove() {
    if (!confirm(`Supprimer définitivement « ${displayName(s)} », ses photos et son journal ?\n\nPour garder l'historique, préférez le statut « Mort » ou « Arraché ».`)) return;
    const r = await guard(() => api.del(`specimens/${id}`), 'Plante supprimée');
    if (r !== undefined) { await refreshSpecimens(); go('/liste'); }
  }

  let sp = $derived(s?.species);
  let attrs = $derived(sp?.attrs || {});
  let cover = $derived(s?.photos?.at(-1));
  let status = $derived(app.meta.statuses.find((x) => x.key === s?.status));
  let age = $derived(s ? ageYears(s) : null);
  let exposureMismatch = $derived(s?.exposure && attrs.exposure?.length && !attrs.exposure.includes(s.exposure));
  let speciesEmpty = $derived(sp && Object.keys(attrs).length === 0);
  let fieldsBySection = $derived.by(() => {
    const out = [];
    for (const f of app.meta.species_fields) {
      const v = attrs[f.key];
      if (v == null || v === '' || (Array.isArray(v) && !v.length)) continue;
      let txt = v;
      if (f.type === 'months') txt = fmtMonths(v);
      else if (f.type === 'multi') txt = v.join(', ');
      else if (f.type === 'bool') txt = v ? 'Oui' : 'Non';
      else if (f.type === 'number') txt = `${String(v).replace('.', ',')}${f.unit ? ' ' + f.unit : ''}`;
      let sec = out.find((x) => x.name === f.section);
      if (!sec) out.push((sec = { name: f.section, items: [] }));
      sec.items.push({ label: f.label, txt, long: f.type === 'textarea', ai: sp.attr_meta?.[f.key]?.source });
    }
    return out;
  });
  const sourceLabel = { gps: 'GPS', manual: 'placée à la main', coords: 'coordonnées saisies', tracker: 'app Home Assistant' };
  const fmtSource = (src) => (src || '').split('+').map((p) => (p === 'ajusté' ? 'ajustée à la main' : sourceLabel[p] || p)).join(', ');
</script>

{#if notFound}
  <div class="page"><p>Plante introuvable.</p><button onclick={() => go('/liste')}>Retour à la liste</button></div>
{:else if !s}
  <div class="page"><p class="muted">Chargement…</p></div>
{:else}
  <div class="page">
    <div class="hero" class:noimg={!cover}>
      {#if cover}<img src={photoUrl(cover.id, 'md')} alt="" />{:else}<span class="big" aria-hidden="true">{CATEGORY_ICON[s.category] || '🪴'}</span>{/if}
      <button class="back icon" aria-label="Retour" onclick={() => history.length > 1 ? history.back() : go('/liste')}>‹</button>
    </div>

    <header class="head">
      <div class="row">
        <h1 class="grow">{displayName(s)}</h1>
        <span class="pill" class:ok={s.status === 'en_place'} class:warn={s.status === 'malade'} class:dead={!ACTIVE_STATUSES.has(s.status)}>{status?.label}</span>
      </div>
      {#if sp}
        <p><button class="link" onclick={() => go(`/espece/${sp.id}`, { retour: id })}>
          {s.nickname ? sp.common_name : ''}{sp.cultivar ? ` ‘${sp.cultivar}’` : ''} {#if sp.botanical_name}<em>{sp.botanical_name}</em>{/if}
          {#if !s.nickname && !sp.cultivar && !sp.botanical_name}Fiche de l'espèce{/if} ›
        </button></p>
      {/if}
      <div class="row small-text muted">
        {#if age}<span>🎂 {fmtAge(age)}{s.planted_on ? ` · plantée le ${fmtDate(s.planted_on)}` : ''}</span>{/if}
        {#if s.origin}<span>· {s.origin}</span>{/if}
        {#if s.zones?.length}<span>· 📍 {s.zones[0].name || kindOf(app.meta, s.zones[0].kind).label}</span>{/if}
        {#if s.irrigation_zone}<span>· 💧 {s.irrigation_zone}</span>{/if}
      </div>
      {#if s.tags?.length}<div class="chips">{#each s.tags as t}<span class="pill">{t}</span>{/each}</div>{/if}
    </header>

    <div class="quick">
      <label class="btn primary">📷 {uploading ? 'Envoi…' : 'Photo'}
        <input type="file" accept="image/*" capture="environment" hidden disabled={uploading} onchange={addPhotos} />
      </label>
      <label class="btn">🖼️ Galerie
        <input type="file" accept="image/*" multiple hidden disabled={uploading} onchange={addPhotos} />
      </label>
      <button onclick={() => go(`/plante/${id}/modifier`)}>✏️ Modifier</button>
      <button onclick={() => go('/', s.lat != null ? { centrer: id } : { deplacer: id })}>🗺️ {s.lat != null ? 'Sur la carte' : 'Placer'}</button>
    </div>

    {#if s.open_issues}
      <div class="notice">⚠️ {s.open_issues} problème{s.open_issues > 1 ? 's' : ''} en cours : voir le journal.</div>
    {/if}
    {#if exposureMismatch}
      <div class="notice">Exposition constatée « {s.exposure} » alors que l'espèce préfère : {attrs.exposure.join(', ')}.</div>
    {/if}
    {#if route.query.nouvelle_espece || speciesEmpty}
      <div class="notice info">
        La fiche de l'espèce « {sp?.common_name} » est vide.
        <button class="small" onclick={() => go(`/espece/${sp.id}`, { retour: id })}>{app.meta.ai_enabled ? "La compléter (avec l'IA)" : 'La compléter'}</button>
      </div>
    {/if}

    <section class="card">
      <h2>Photos</h2>
      <PhotoTimeline photos={s.photos} onchange={reload} />
    </section>

    <section class="card">
      <h2>Journal</h2>
      <Journal specimenId={id} events={s.events} photos={s.photos} onchange={reload} onphotos={load} />
    </section>

    {#if s.exposure || s.soil || s.notes}
      <section class="card">
        <h2>Cet emplacement</h2>
        <dl>
          {#if s.exposure}<dt>Exposition</dt><dd>{s.exposure}</dd>{/if}
          {#if s.soil}<dt>Sol</dt><dd>{s.soil}</dd>{/if}
        </dl>
        {#if s.notes}<p class="pre">{s.notes}</p>{/if}
      </section>
    {/if}

    {#if fieldsBySection.length}
      <section class="card">
        <div class="row"><h2 class="grow">Fiche de l'espèce</h2><button class="small" onclick={() => go(`/espece/${sp.id}`, { retour: id })}>Modifier</button></div>
        {#each fieldsBySection as sec}
          <h3>{sec.name}</h3>
          <dl>
            {#each sec.items as it}
              <dt>{it.label}{#if it.ai} <span class="pill ai" title={it.ai}>IA</span>{/if}</dt><dd class:pre={it.long}>{it.txt}</dd>
            {/each}
          </dl>
        {/each}
      </section>
    {/if}

    <section class="card">
      <h2>Emplacement</h2>
      {#if s.lat != null}
        {#if s.zones?.length}
          <div class="chips">
            {#each s.zones as z}
              {@const k = kindOf(app.meta, z.kind)}
              <span class="pill"><span class="sw" style="background:{k.color}"></span>{z.name || k.label}</span>
            {/each}
          </div>
        {/if}
        <p class="small-text muted">
          {s.lat.toFixed(6)}, {s.lon.toFixed(6)} · {fmtSource(s.position_source)}{s.gps_accuracy ? ` (±${fmtMeters(s.gps_accuracy)})` : ''}
        </p>
      {:else}
        <p class="muted small-text">Pas encore placée sur la carte.</p>
      {/if}
      {#if s.positions.length > 1}
        <details><summary class="small-text">Historique des positions ({s.positions.length})</summary>
          <ul class="small-text">{#each s.positions as p}<li>{fmtDate(p.moved_at.slice(0, 10))} — {p.reason || ''}</li>{/each}</ul>
        </details>
      {/if}
      <div class="row">
        <button class="small" onclick={() => go('/', { deplacer: id })}>Déplacer</button>
        <button class="small" onclick={() => go('/', { dupliquer: id })}>Dupliquer à côté</button>
        <span class="grow"></span>
        <button class="small danger" onclick={remove}>Supprimer</button>
      </div>
    </section>
  </div>
{/if}

<style>
  .hero { margin: -16px -16px 0; height: 240px; position: relative; background: var(--leaf-soft); display: grid; place-items: center; overflow: hidden; }
  .hero img { width: 100%; height: 100%; object-fit: cover; }
  .hero.noimg { height: 140px; }
  .hero .big { font-size: 64px; }
  .back { position: absolute; top: 12px; left: 12px; background: color-mix(in srgb, var(--surface) 85%, transparent); font-size: 1.6rem; }
  .head { display: grid; gap: 6px; }
  .link { border: 0; background: none; padding: 0; min-height: 0; color: var(--leaf); font-weight: 600; white-space: normal; text-align: left; }
  .quick { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; }
  .quick > * { padding: 0 6px; font-size: 0.88rem; }
  @media (max-width: 420px) { .quick { grid-template-columns: 1fr 1fr; } }
  dl { display: grid; grid-template-columns: minmax(110px, 40%) 1fr; gap: 6px 12px; margin: 0; }
  dt { color: var(--ink-2); font-size: 0.9rem; }
  dd { margin: 0; }
  .pre { white-space: pre-line; }
  details ul { margin: 6px 0 0; padding-left: 18px; }
  .sw { width: 12px; height: 12px; border-radius: 3px; border: 1px solid rgb(0 0 0 / 0.15); display: inline-block; }
</style>
