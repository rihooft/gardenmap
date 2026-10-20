<script>
  import { api, photoUrl, uploadPhotos } from '../lib/api.js';
  import { fmtDate } from '../lib/format.js';
  import { guard, toast } from '../lib/store.svelte.js';

  /** event : problème du journal ; photos : photos de la plante ; onsaved() / onclose() */
  let { event, specimenId, photos, onsaved, onclose, onphotos } = $props();

  const MAX = 4;
  let picked = $state(event.photo_id ? [event.photo_id] : []);
  let busy = $state(false);
  let uploading = $state(false);
  let result = $state(null);
  let chosen = $state(0); // hypothèse retenue pour le titre
  let error = $state(null);

  // photos proches de la date du problème en premier
  let candidates = $derived(
    [...photos].sort((a, b) => Math.abs(Date.parse(a.taken_at) - Date.parse(event.date)) - Math.abs(Date.parse(b.taken_at) - Date.parse(event.date))).slice(0, 12),
  );

  function toggle(id) {
    if (picked.includes(id)) picked = picked.filter((x) => x !== id);
    else if (picked.length < MAX) picked = [...picked, id];
    else toast(`${MAX} photos au maximum`, 'error');
  }

  async function addPhoto(e) {
    const files = [...(e.currentTarget.files || [])];
    e.currentTarget.value = '';
    if (!files.length) return;
    uploading = true;
    const r = await guard(() => uploadPhotos(specimenId, files, event.title || event.type));
    uploading = false;
    if (r?.photos.length) {
      picked = [...picked, ...r.photos.map((p) => p.id)].slice(-MAX);
      await onphotos?.();
    }
  }

  async function run() {
    busy = true;
    error = null;
    try {
      result = await api.post(`events/${event.id}/diagnose`, { photo_ids: picked });
      chosen = 0;
    } catch (e) {
      error = e.message;
    } finally {
      busy = false;
    }
  }

  async function save() {
    const h = result.hypotheses[chosen];
    const body = { diagnosis: { ...$state.snapshot(result), retained: chosen } };
    if (h && (!event.title || confirm(`Remplacer le titre « ${event.title} » par « ${h.name} » ?`))) body.title = h.name;
    const r = await guard(() => api.put(`events/${event.id}`, body), 'Diagnostic enregistré dans le journal');
    if (r) onsaved?.();
  }

  const confClass = { haute: 'ok', moyenne: 'warn', faible: '' };
  const typeLabel = { maladie: 'Maladie', ravageur: 'Ravageur', carence: 'Carence', 'non parasitaire': 'Cause non parasitaire', autre: 'Autre' };
</script>

<div class="panel">
  <div class="row">
    <strong class="grow">🔬 Diagnostic : {event.title || event.type}</strong>
    <button class="ghost small" aria-label="Fermer" onclick={() => onclose?.()}>✕</button>
  </div>

  {#if !result}
    <p class="muted small-text">Choisissez 1 à {MAX} photos nettes du symptôme : une vue d'ensemble et des gros plans (dessus et revers des feuilles).</p>
    <div class="pick">
      {#each candidates as p (p.id)}
        <button class="ph" class:on={picked.includes(p.id)} aria-pressed={picked.includes(p.id)} onclick={() => toggle(p.id)}>
          <img src={photoUrl(p.id, 'th')} alt="" />
          <span>{fmtDate(p.taken_at.slice(0, 10))}</span>
          {#if picked.includes(p.id)}<b>{picked.indexOf(p.id) + 1}</b>{/if}
        </button>
      {/each}
      <label class="ph add">
        <span class="plus">{uploading ? '…' : '📷'}</span><span>{uploading ? 'Envoi' : 'Nouvelle photo'}</span>
        <input type="file" accept="image/*" capture="environment" hidden disabled={uploading} onchange={addPhoto} />
      </label>
    </div>
    {#if error}<div class="notice">{error}</div>{/if}
    <button class="ai" disabled={!picked.length || busy} onclick={run}>
      {busy ? "Analyse en cours… (20 à 40 s)" : `Analyser ${picked.length || ''} photo${picked.length > 1 ? 's' : ''}`}
    </button>
  {:else}
    {#if !result.plant_visible}
      <div class="notice">Le symptôme n'est pas assez visible sur ces photos. {result.advice || ''}</div>
    {/if}
    {#if result.symptoms}<p class="small-text"><span class="muted">Observé :</span> {result.symptoms}</p>{/if}
    {#if result.urgency}
      <span class="pill" class:warn={result.urgency !== 'faible'} class:ok={result.urgency === 'faible'}>Urgence {result.urgency}</span>
    {/if}

    <ol class="hyps">
      {#each result.hypotheses as h, i}
        <li class:on={chosen === i}>
          <label class="head">
            <input type="radio" name="hyp-{event.id}" checked={chosen === i} onchange={() => (chosen = i)} />
            <span class="grow"><strong>{h.name}</strong> <span class="muted small-text">{typeLabel[h.type]}</span></span>
            <span class="pill {confClass[h.confidence]}">{h.confidence}</span>
          </label>
          {#if h.evidence}<p class="small-text"><span class="muted">Indices :</span> {h.evidence}</p>{/if}
          {#if h.check}<p class="small-text"><span class="muted">Pour confirmer :</span> {h.check}</p>{/if}
          {#if h.actions.length}
            <p class="small-text muted">Que faire :</p>
            <ul class="small-text">{#each h.actions as a}<li>{a}</li>{/each}</ul>
          {/if}
          {#if h.prevention}<p class="small-text"><span class="muted">Prévention :</span> {h.prevention}</p>{/if}
        </li>
      {/each}
    </ol>
    {#if result.advice && result.plant_visible}<p class="small-text">💡 {result.advice}</p>{/if}
    <p class="muted small-text">Hypothèses d'une IA à partir de photos : vérifiez sur place avant de traiter, et lisez l'étiquette de tout produit.</p>
    <div class="row">
      {#if result.hypotheses.length}<button class="primary grow" onclick={save}>Enregistrer dans le journal</button>{/if}
      <button class="small" onclick={() => (result = null)}>Autres photos</button>
    </div>
    <p class="muted small-text">Source : {result.source}</p>
  {/if}
</div>

<style>
  .panel { display: grid; gap: 10px; padding: 14px; border-radius: 12px; background: var(--ai-soft); border: 1px solid color-mix(in srgb, var(--ai) 35%, transparent); }
  .pick { display: flex; gap: 8px; overflow-x: auto; padding-bottom: 4px; }
  .ph { flex: none; width: 88px; display: grid; gap: 2px; padding: 0; border: 0; background: none; min-height: 0; font-weight: 500; position: relative; justify-items: center; cursor: pointer; }
  .ph img, .ph .plus { width: 88px; height: 88px; object-fit: cover; border-radius: 10px; display: grid; place-items: center; background: var(--surface); font-size: 1.6rem; }
  .ph span { font-size: 0.72rem; color: var(--ink-2); }
  .ph.on img { outline: 4px solid var(--ai); outline-offset: -4px; }
  .ph b { position: absolute; top: 4px; right: 4px; width: 22px; height: 22px; border-radius: 50%; background: var(--ai); color: #fff; font-size: 0.8rem; display: grid; place-items: center; }
  .hyps { margin: 0; padding: 0; list-style: none; display: grid; gap: 8px; }
  .hyps > li { background: var(--surface); border-radius: 10px; padding: 10px 12px; display: grid; gap: 4px; border: 2px solid transparent; }
  .hyps > li.on { border-color: var(--ai); }
  .head { display: flex; gap: 8px; align-items: center; }
  .head input { width: 20px; min-height: 20px; height: 20px; accent-color: var(--ai); flex: none; }
  ul { margin: 0; padding-left: 20px; }
</style>
