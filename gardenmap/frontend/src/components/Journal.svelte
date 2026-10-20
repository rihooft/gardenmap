<script>
  import { api, uploadPhotos } from '../lib/api.js';
  import { fmtDate, today } from '../lib/format.js';
  import { app, guard } from '../lib/store.svelte.js';
  import DiagnosisPanel from './DiagnosisPanel.svelte';

  let { specimenId, events, photos = [], onchange, onphotos } = $props();
  let diagnosing = $state(null); // id du problème en cours de diagnostic
  let expanded = $state({}); // diagnostics enregistrés dépliés

  const KINDS = {
    intervention: { label: 'Intervention', icon: '✂️', types: ['Taille', 'Arrosage', 'Engrais', 'Traitement', 'Paillage', 'Protection hivernale', 'Récolte', 'Rempotage', 'Autre'] },
    observation: { label: 'Problème', icon: '⚠️', types: ['Maladie', 'Ravageur', 'Carence', 'Dégât (gel, vent…)', 'Autre'] },
    measure: { label: 'Mesure', icon: '📏', types: ['Hauteur', 'Envergure', 'Circonférence du tronc', 'Récolte (poids)'] },
  };
  const UNITS = { Hauteur: 'm', Envergure: 'm', 'Circonférence du tronc': 'cm', 'Récolte (poids)': 'kg' };

  let form = $state(null);
  let photoFile = $state(null);
  let filter = $state('all');

  function start(kind) {
    form = { kind, date: today(), type: KINDS[kind].types[0], title: '', notes: '', product: '', quantity: '', value: '', severity: 'moyenne' };
    photoFile = null;
  }

  async function save(e) {
    e.preventDefault();
    const body = { ...form };
    if (form.kind === 'measure') body.unit = UNITS[form.type] || '';
    const r = await guard(async () => {
      if (photoFile) {
        const up = await uploadPhotos(specimenId, [photoFile], form.title || form.type);
        body.photo_id = up.photos[0]?.id ?? null;
      }
      return api.post(`specimens/${specimenId}/events`, body);
    }, 'Ajouté au journal');
    if (r) {
      const withPhoto = form.kind === 'observation' && body.photo_id;
      form = null;
      await onchange?.();
      // un problème photographié : on propose tout de suite le diagnostic
      if (withPhoto && app.meta?.ai_enabled) diagnosing = r.id;
    }
  }

  async function toggleResolved(ev) {
    const r = await guard(() => api.put(`events/${ev.id}`, { status: ev.status === 'resolu' ? 'ouvert' : 'resolu' }));
    if (r) onchange?.();
  }

  async function remove(ev) {
    if (!confirm('Supprimer cette entrée du journal ?')) return;
    const r = await guard(() => api.del(`events/${ev.id}`));
    if (r !== undefined) onchange?.();
  }

  let shown = $derived(filter === 'all' ? events : events.filter((e) => e.kind === filter));
  const fmtNum = (v) => String(v).replace('.', ',');
</script>

<div class="row">
  {#each Object.entries(KINDS) as [k, d]}
    <button class="small" onclick={() => start(k)}>{d.icon} {d.label}</button>
  {/each}
</div>

{#if form}
  <form class="add" onsubmit={save}>
    <strong>{KINDS[form.kind].icon} {KINDS[form.kind].label}</strong>
    <div class="grid2">
      <label class="field">Date <input type="date" bind:value={form.date} max={today()} required /></label>
      <label class="field">Type <select bind:value={form.type}>{#each KINDS[form.kind].types as t}<option>{t}</option>{/each}</select></label>
    </div>
    {#if form.kind === 'measure'}
      <label class="field">Valeur ({UNITS[form.type]}) <input type="number" step="any" inputmode="decimal" bind:value={form.value} required /></label>
    {:else}
      <label class="field">{form.kind === 'observation' ? 'Symptôme, maladie ou ravageur suspecté' : 'Résumé'}
        <input bind:value={form.title} placeholder={form.kind === 'observation' ? 'Taches orange sur les feuilles (rouille ?)' : 'Taille de formation'} />
      </label>
      {#if form.kind === 'intervention'}
        <div class="grid2">
          <label class="field">Produit <input bind:value={form.product} placeholder="bouillie bordelaise" /></label>
          <label class="field">Quantité <input bind:value={form.quantity} placeholder="20 g / 10 L" /></label>
        </div>
      {:else}
        <label class="field">Gravité
          <select bind:value={form.severity}><option value="faible">Faible</option><option value="moyenne">Moyenne</option><option value="forte">Forte</option></select>
        </label>
      {/if}
    {/if}
    <label class="field">Notes <textarea bind:value={form.notes} rows="2"></textarea></label>
    <label class="btn small">📷 {photoFile ? photoFile.name : 'Joindre une photo'}
      <input type="file" accept="image/*" hidden onchange={(e) => (photoFile = e.currentTarget.files?.[0] || null)} />
    </label>
    <div class="row"><button class="primary grow" type="submit">Ajouter</button><button class="ghost" type="button" onclick={() => (form = null)}>Annuler</button></div>
  </form>
{/if}

{#if events.length}
  <div class="chips">
    <button class="chip" class:on={filter === 'all'} onclick={() => (filter = 'all')}>Tout</button>
    {#each Object.entries(KINDS) as [k, d]}
      {#if events.some((e) => e.kind === k)}<button class="chip" class:on={filter === k} onclick={() => (filter = k)}>{d.label}s</button>{/if}
    {/each}
  </div>
  <ul class="log">
    {#each shown as ev (ev.id)}
      <li class:resolved={ev.kind === 'observation' && ev.status === 'resolu'}>
        <span class="ic" aria-hidden="true">{KINDS[ev.kind]?.icon}</span>
        <div class="grow body">
          <div class="row tight">
            <strong>{ev.kind === 'measure' ? `${ev.type} : ${fmtNum(ev.value)} ${ev.unit || ''}` : ev.title || ev.type}</strong>
            {#if ev.kind === 'observation'}
              <span class="pill" class:warn={ev.status !== 'resolu'} class:ok={ev.status === 'resolu'}>{ev.status === 'resolu' ? 'Résolu' : `Ouvert · ${ev.severity || ''}`}</span>
            {/if}
          </div>
          <span class="muted small-text">{fmtDate(ev.date)}{ev.kind !== 'measure' && ev.title ? ` · ${ev.type}` : ''}{ev.product ? ` · ${ev.product}` : ''}{ev.quantity ? ` (${ev.quantity})` : ''}</span>
          {#if ev.notes}<p class="small-text">{ev.notes}</p>{/if}
          {#if ev.diagnosis?.hypotheses?.length}
            {@const d = ev.diagnosis}
            {@const h = d.hypotheses[d.retained ?? 0]}
            <button class="diag-sum" onclick={() => (expanded[ev.id] = !expanded[ev.id])} aria-expanded={!!expanded[ev.id]}>
              🔬 {h.name} · confiance {h.confidence} {expanded[ev.id] ? '▴' : '▾'}
            </button>
            {#if expanded[ev.id]}
              <div class="diag small-text">
                {#if h.check}<p><span class="muted">Pour confirmer :</span> {h.check}</p>{/if}
                {#if h.actions?.length}<p class="muted">Que faire :</p><ul>{#each h.actions as a}<li>{a}</li>{/each}</ul>{/if}
                {#if h.prevention}<p><span class="muted">Prévention :</span> {h.prevention}</p>{/if}
                {#if d.hypotheses.length > 1}
                  <p class="muted">Autres pistes : {d.hypotheses.filter((_, i) => i !== (d.retained ?? 0)).map((x) => `${x.name} (${x.confidence})`).join(' ; ')}</p>
                {/if}
                <p class="muted">{d.source} · {fmtDate(d.generated_at?.slice(0, 10))}</p>
              </div>
            {/if}
          {/if}
          {#if ev.kind === 'observation' && app.meta?.ai_enabled && diagnosing !== ev.id && ev.status !== 'resolu'}
            <button class="small ai diag-btn" onclick={() => (diagnosing = ev.id)}>🔬 {ev.diagnosis ? 'Nouveau diagnostic' : 'Diagnostic IA'}</button>
          {/if}
        </div>
        <div class="acts">
          {#if ev.kind === 'observation'}<button class="small" onclick={() => toggleResolved(ev)}>{ev.status === 'resolu' ? 'Rouvrir' : 'Résolu'}</button>{/if}
          <button class="small ghost" aria-label="Supprimer" onclick={() => remove(ev)}>✕</button>
        </div>
      </li>
      {#if diagnosing === ev.id}
        <li class="diag-row">
          <DiagnosisPanel event={ev} {specimenId} {photos} {onphotos}
            onsaved={async () => { diagnosing = null; expanded[ev.id] = true; await onchange?.(); }}
            onclose={() => (diagnosing = null)} />
        </li>
      {/if}
    {/each}
  </ul>
{:else if !form}
  <p class="muted small-text">Rien encore : notez ici les tailles, traitements, problèmes observés et mesures.</p>
{/if}

<style>
  .add { display: grid; gap: 10px; padding: 14px; border-radius: 12px; background: var(--surface-2); }
  .log { list-style: none; margin: 0; padding: 0; display: grid; }
  .log > li { display: flex; gap: 10px; padding: 10px 0; border-bottom: 1px solid var(--line); align-items: flex-start; }
  .log > li.resolved { opacity: 0.65; }
  .ic { font-size: 1.2rem; width: 28px; text-align: center; }
  .body { display: grid; gap: 2px; }
  .tight { gap: 6px; }
  .acts { display: flex; gap: 4px; }
  .log > li.diag-row { display: block; border-bottom: 0; }
  .diag-sum { justify-self: start; min-height: 32px; padding: 0 10px; font-size: 0.85rem; background: var(--ai-soft); color: var(--ai); border-color: transparent; white-space: normal; text-align: left; margin-top: 4px; }
  .diag { display: grid; gap: 4px; padding: 8px 10px; border-left: 3px solid var(--ai); margin-top: 4px; }
  .diag ul { margin: 0; padding-left: 18px; }
  .diag-btn { justify-self: start; margin-top: 6px; }
</style>
