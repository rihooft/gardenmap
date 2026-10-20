<script>
  import { photoUrl, api } from '../lib/api.js';
  import { fmtDate, MONTHS } from '../lib/format.js';
  import { guard } from '../lib/store.svelte.js';

  /** photos triées par date croissante ; onchange() après une modification. */
  let { photos, onchange } = $props();

  let viewer = $state(null); // index affiché en plein écran
  let compare = $state(false);
  let picked = $state([]); // ids choisis pour la comparaison
  let editing = $state(null);

  let years = $derived.by(() => {
    const groups = new Map();
    photos.forEach((p, i) => {
      const y = p.taken_at.slice(0, 4);
      if (!groups.has(y)) groups.set(y, []);
      groups.get(y).push({ ...p, index: i });
    });
    return [...groups.entries()].reverse(); // année la plus récente en haut
  });

  function open(i) {
    if (compare) {
      const id = photos[i].id;
      picked = picked.includes(id) ? picked.filter((x) => x !== id) : [...picked, id].slice(-2);
      return;
    }
    viewer = i;
    editing = null;
  }

  function step(d) {
    viewer = (viewer + d + photos.length) % photos.length;
    editing = null;
  }

  function onKey(e) {
    if (viewer == null) return;
    if (e.key === 'ArrowRight') step(1);
    else if (e.key === 'ArrowLeft') step(-1);
    else if (e.key === 'Escape') viewer = null;
  }

  let touchX = null;
  const touchStart = (e) => (touchX = e.touches[0].clientX);
  function touchEnd(e) {
    if (touchX == null) return;
    const dx = e.changedTouches[0].clientX - touchX;
    if (Math.abs(dx) > 50) step(dx < 0 ? 1 : -1);
    touchX = null;
  }

  function startEdit() {
    const p = photos[viewer];
    editing = { taken_at: p.taken_at.slice(0, 16), caption: p.caption || '' };
  }

  async function saveEdit() {
    const p = photos[viewer];
    const r = await guard(() => api.put(`photos/${p.id}`, { taken_at: editing.taken_at, caption: editing.caption }), 'Photo modifiée');
    if (r) { editing = null; viewer = null; onchange?.(); }
  }

  async function remove() {
    const p = photos[viewer];
    if (!confirm('Supprimer définitivement cette photo ?')) return;
    const r = await guard(() => api.del(`photos/${p.id}`), 'Photo supprimée');
    if (r !== undefined) { viewer = null; onchange?.(); }
  }

  let pair = $derived(picked.map((id) => photos.find((p) => p.id === id)).filter(Boolean).sort((a, b) => a.taken_at.localeCompare(b.taken_at)));
  const shortDate = (iso) => `${+iso.slice(8, 10)} ${MONTHS.at(+iso.slice(5, 7) - 1)}`;
</script>

<svelte:window onkeydown={onKey} />

{#if photos.length}
  <div class="row">
    <span class="muted small-text grow">{photos.length} photo{photos.length > 1 ? 's' : ''}, du {fmtDate(photos[0].taken_at.slice(0, 10))} au {fmtDate(photos.at(-1).taken_at.slice(0, 10))}</span>
    {#if photos.length > 1}
      <button class="small" class:primary={compare} onclick={() => { compare = !compare; picked = []; }}>{compare ? 'Terminer' : 'Comparer'}</button>
    {/if}
  </div>
  {#if compare}<p class="muted small-text">Touchez deux photos à comparer.</p>{/if}

  {#if compare && pair.length === 2}
    <div class="compare">
      {#each pair as p}
        <figure><img src={photoUrl(p.id, 'md')} alt="" /><figcaption>{fmtDate(p.taken_at.slice(0, 10))}</figcaption></figure>
      {/each}
    </div>
  {/if}

  <div class="strip">
    {#each years as [year, list]}
      <span class="yr" aria-hidden="true">{year}</span>
      {#each [...list].reverse() as p}
        <button class="thumb" class:picked={picked.includes(p.id)} onclick={() => open(p.index)} aria-label="Photo du {fmtDate(p.taken_at.slice(0, 10))}">
          <img src={photoUrl(p.id, 'th')} alt="" loading="lazy" />
          <span>{shortDate(p.taken_at)}</span>
        </button>
      {/each}
    {/each}
  </div>
{:else}
  <p class="muted small-text">Pas encore de photo. Une photo par saison permet de suivre la croissance.</p>
{/if}

{#if viewer != null}
  {@const p = photos[viewer]}
  <div class="lightbox" role="dialog" aria-label="Photo" tabindex="-1" ontouchstart={touchStart} ontouchend={touchEnd}>
    <div class="top">
      <span class="grow"><strong>{fmtDate(p.taken_at, true)}</strong>
        <span class="src">{p.taken_source === 'exif' ? 'date de prise de vue' : p.taken_source === 'manual' ? 'date corrigée' : "date d'import"}</span></span>
      <button class="icon ghost" aria-label="Fermer" onclick={() => (viewer = null)}>✕</button>
    </div>
    <div class="stage">
      <img src={photoUrl(p.id, 'md')} alt={p.caption || ''} />
      {#if photos.length > 1 && !editing}
        <button class="nav prev icon" aria-label="Photo précédente" onclick={() => step(-1)}>‹</button>
        <button class="nav next icon" aria-label="Photo suivante" onclick={() => step(1)}>›</button>
      {/if}
    </div>
    {#if editing}
      <div class="edit">
        <input type="datetime-local" bind:value={editing.taken_at} />
        <input placeholder="Légende" bind:value={editing.caption} />
        <div class="row"><button class="primary grow" onclick={saveEdit}>Enregistrer</button><button class="ghost" onclick={() => (editing = null)}>Annuler</button></div>
      </div>
    {:else}
      {#if p.caption}<p class="caption">{p.caption}</p>{/if}
      <div class="bottom">
        <span class="grow">{viewer + 1} / {photos.length}</span>
        <button class="small" onclick={startEdit}>Date, légende</button>
        <a class="btn small" href={photoUrl(p.id, 'orig')} target="_blank" rel="noopener">Original</a>
        <button class="small danger" onclick={remove}>Supprimer</button>
      </div>
    {/if}
  </div>
{/if}

<style>
  .yr { flex: none; writing-mode: vertical-rl; transform: rotate(180deg); font-weight: 800; color: var(--ink-2); font-size: 0.85rem; align-self: stretch; text-align: center; border-left: 2px solid var(--line); padding: 0 2px; }
  .strip { display: flex; gap: 8px; overflow-x: auto; padding-bottom: 4px; }
  .thumb { flex: none; display: grid; gap: 2px; padding: 0; border: 0; background: none; min-height: 0; border-radius: 10px; font-weight: 500; }
  .thumb img { width: 104px; height: 104px; object-fit: cover; border-radius: 10px; display: block; }
  .thumb span { font-size: 0.78rem; color: var(--ink-2); }
  .thumb.picked img { outline: 4px solid var(--leaf); outline-offset: -4px; }
  .compare { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
  .compare figure { margin: 0; }
  .compare img { width: 100%; aspect-ratio: 3 / 4; object-fit: cover; border-radius: 10px; display: block; }
  .compare figcaption { font-size: 0.82rem; text-align: center; color: var(--ink-2); }
  .lightbox { position: fixed; inset: 0; z-index: 3000; background: #0b0e0b; color: #eee; display: grid; grid-template-rows: auto 1fr auto auto; }
  .stage { position: relative; min-height: 0; }
  .stage img { width: 100%; height: 100%; object-fit: contain; display: block; }
  .nav { position: absolute; top: 50%; transform: translateY(-50%); font-size: 1.8rem; background: rgb(0 0 0 / 0.45) !important; border: 0 !important; }
  .nav.prev { left: 8px; }
  .nav.next { right: 8px; }
  .top, .bottom { display: flex; align-items: center; gap: 8px; padding: 10px 12px; }
  .bottom { padding-bottom: calc(10px + env(safe-area-inset-bottom)); flex-wrap: wrap; }
  .top .src { display: block; font-size: 0.8rem; color: #aaa; }
  .lightbox button, .lightbox .btn { background: #222; color: #eee; border-color: #333; }
  .center { text-align: center; }
  .caption { padding: 0 14px; color: #ddd; }
  .edit { display: grid; gap: 8px; padding: 12px; }
</style>
