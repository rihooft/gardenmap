<script>
  import { app, go } from '../lib/store.svelte.js';
  import { photoUrl } from '../lib/api.js';
  import { CATEGORY_ICON, ACTIVE_STATUSES, displayName, ageYears, fmtAge } from '../lib/format.js';

  let q = $state('');
  let cat = $state(null);
  let issues = $state(false);
  let archived = $state(false);

  const norm = (t) => (t || '').normalize('NFD').replace(/\p{M}/gu, '').toLowerCase();

  let filtered = $derived(
    app.specimens.filter((s) => {
      if (!archived && !ACTIVE_STATUSES.has(s.status)) return false;
      if (archived && ACTIVE_STATUSES.has(s.status)) return false;
      if (cat && s.category !== cat) return false;
      if (issues && !s.open_issues) return false;
      if (q) {
        const hay = norm([s.nickname, s.common_name, s.botanical_name, s.cultivar, s.irrigation_zone, ...(s.tags || [])].join(' '));
        if (!norm(q).split(/\s+/).every((w) => hay.includes(w))) return false;
      }
      return true;
    }),
  );

  let groups = $derived.by(() => {
    const m = new Map();
    for (const s of filtered) {
      const k = s.category || 'autre';
      if (!m.has(k)) m.set(k, []);
      m.get(k).push(s);
    }
    const order = app.meta.categories.map((c) => c.key);
    return [...m.entries()].sort((a, b) => order.indexOf(a[0]) - order.indexOf(b[0]));
  });

  let catsPresent = $derived([...new Set(app.specimens.filter((s) => ACTIVE_STATUSES.has(s.status)).map((s) => s.category || 'autre'))]);
  const catLabel = (k) => app.meta.categories.find((c) => c.key === k)?.label || k;
  let archivedCount = $derived(app.specimens.filter((s) => !ACTIVE_STATUSES.has(s.status)).length);
</script>

<div class="page">
  <div class="row">
    <h1 class="grow">Plantes du jardin</h1>
    <button class="small" onclick={() => go('/nouvelle')}>＋ Sans position</button>
  </div>

  <input type="search" placeholder="Rechercher : nom, variété, zone, étiquette…" bind:value={q} />

  <div class="chips">
    <button class="chip" class:on={!cat && !issues} onclick={() => { cat = null; issues = false; }}>Toutes</button>
    <button class="chip" class:on={issues} onclick={() => (issues = !issues)}>⚠️ Problèmes</button>
    {#each catsPresent as c}
      <button class="chip" class:on={cat === c} onclick={() => (cat = cat === c ? null : c)}>{CATEGORY_ICON[c]} {catLabel(c)}</button>
    {/each}
    {#if archivedCount}
      <button class="chip" class:on={archived} onclick={() => (archived = !archived)}>Archivées ({archivedCount})</button>
    {/if}
  </div>

  {#if !app.specimens.length}
    <div class="card"><p>Aucune plante pour l'instant.</p><p class="muted small-text">Sur le plan, touchez « ＋ Plante ici » au pied d'une plante pour l'ajouter avec sa position.</p>
      <button class="primary" onclick={() => go('/')}>Aller au plan</button></div>
  {:else if !filtered.length}
    <p class="muted">Aucune plante ne correspond.</p>
  {/if}

  {#each groups as [k, list]}
    <section class="group">
      <h3>{CATEGORY_ICON[k]} {catLabel(k)} · {list.length}</h3>
      {#each list as s (s.id)}
        <button class="item" onclick={() => go(`/plante/${s.id}`)}>
          {#if s.cover_photo_id}<img src={photoUrl(s.cover_photo_id, 'th')} alt="" loading="lazy" />{:else}<span class="ph">{CATEGORY_ICON[s.category] || '🪴'}</span>{/if}
          <span class="txt">
            <strong>{displayName(s)}</strong>
            <span class="muted small-text">
              {[s.nickname ? s.common_name : null, s.cultivar ? `‘${s.cultivar}’` : null].filter(Boolean).join(' ')}
              {#if s.botanical_name}<em>{s.botanical_name}</em>{/if}
            </span>
            <span class="meta small-text">
              {#if ageYears(s)}<span>{fmtAge(ageYears(s))}</span>{/if}
              {#if s.photo_count}<span>📷 {s.photo_count}</span>{/if}
              {#if s.lat == null}<span class="pill">non placée</span>{/if}
              {#if s.open_issues}<span class="pill warn">⚠️ {s.open_issues}</span>{/if}
              {#if s.status === 'malade'}<span class="pill warn">malade</span>{/if}
            </span>
          </span>
          <span aria-hidden="true" class="chev">›</span>
        </button>
      {/each}
    </section>
  {/each}
</div>

<style>
  .group { display: grid; gap: 8px; }
  .item {
    display: flex; align-items: center; gap: 12px; padding: 8px; min-height: 72px; text-align: left; white-space: normal;
    border-radius: 14px; font-weight: 400; justify-content: flex-start;
  }
  .item img, .item .ph { width: 56px; height: 56px; border-radius: 10px; object-fit: cover; flex: none; display: grid; place-items: center; background: var(--surface-2); font-size: 26px; }
  .txt { display: grid; gap: 2px; flex: 1; min-width: 0; }
  .meta { display: flex; gap: 8px; flex-wrap: wrap; color: var(--ink-2); align-items: center; }
  .chev { color: var(--ink-2); font-size: 1.4rem; }
</style>
