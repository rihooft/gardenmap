<script>
  import { app, go, guard, refreshSpecies, refreshSpecimens, toast } from '../lib/store.svelte.js';
  import { api } from '../lib/api.js';
  import { CATEGORY_ICON, fmtMonths, displayName } from '../lib/format.js';
  import FieldInput from '../components/FieldInput.svelte';

  let { id, back = null } = $props();

  let sp = $state(null);
  let saving = $state(false);
  let dirty = $state(false);
  let ai = $state(null); // { proposals, source, confidence, note, decisions: { key: 'accept'|'reject' } }
  let aiBusy = $state(false);

  api.get(`species/${id}`).then((r) => (sp = r)).catch((e) => toast(e.message, 'error'));

  let sections = $derived.by(() => {
    const out = [];
    for (const f of app.meta.species_fields) {
      let s = out.find((x) => x.name === f.section);
      if (!s) out.push((s = { name: f.section, fields: [] }));
      s.fields.push(f);
    }
    return out;
  });

  let specimens = $derived(app.specimens.filter((s) => s.species_id === id));

  const TOP_LABELS = { botanical_name: 'Nom botanique', family: 'Famille', category: 'Catégorie' };
  const fieldOf = (key) => app.meta.species_fields.find((f) => f.key === key);
  function labelOf(key) {
    return TOP_LABELS[key] || fieldOf(key)?.label || key;
  }
  function show(key, v) {
    const f = fieldOf(key);
    if (key === 'category') return `${CATEGORY_ICON[v] || ''} ${app.meta.categories.find((c) => c.key === v)?.label || v}`;
    if (!f) return v;
    if (f.type === 'months') return fmtMonths(v);
    if (f.type === 'multi') return v.join(', ');
    if (f.type === 'bool') return v ? 'Oui' : 'Non';
    if (f.type === 'number') return `${String(v).replace('.', ',')}${f.unit ? ' ' + f.unit : ''}`;
    return v;
  }

  function current(key) {
    return key in TOP_LABELS ? sp[key] : sp.attrs[key];
  }

  async function askAI() {
    if (dirty && !confirm("Enregistrer d'abord vos modifications ?")) return;
    if (dirty) await save(true);
    aiBusy = true;
    const r = await guard(() => api.post(`species/${id}/enrich`));
    aiBusy = false;
    if (!r) return;
    const keys = Object.keys(r.proposals);
    if (!keys.length) return toast("L'IA n'a rien à proposer de nouveau pour cette fiche.");
    ai = { ...r, decisions: Object.fromEntries(keys.map((k) => [k, current(k) == null ? 'accept' : 'reject'])) };
  }

  async function applyAI() {
    const meta = { ...sp.attr_meta };
    let n = 0;
    for (const [k, d] of Object.entries(ai.decisions)) {
      if (d !== 'accept') continue;
      const v = ai.proposals[k];
      if (k in TOP_LABELS) sp[k] = v;
      else sp.attrs[k] = v;
      meta[k] = { source: ai.source, date: ai.generated_at, pending: false };
      n++;
    }
    sp.attr_meta = meta;
    ai = null;
    if (n) {
      await save(false, `${n} champ${n > 1 ? 's' : ''} ajouté${n > 1 ? 's' : ''} depuis l'IA`);
    }
  }

  function edited(key) {
    dirty = true;
    // une valeur retouchée à la main n'est plus « de l'IA »
    if (sp.attr_meta?.[key]) {
      const { [key]: _, ...rest } = sp.attr_meta;
      sp.attr_meta = rest;
    }
  }

  async function save(silent = false, message = 'Fiche espèce enregistrée') {
    saving = true;
    const body = $state.snapshot(sp);
    const r = await guard(() => api.put(`species/${id}`, body), silent ? null : message);
    saving = false;
    if (r) {
      sp = r;
      dirty = false;
      await Promise.all([refreshSpecies(), refreshSpecimens()]);
    }
    return r;
  }

  async function remove() {
    if (!confirm(`Supprimer l'espèce « ${sp.common_name} » ?`)) return;
    const r = await guard(() => api.del(`species/${id}`), 'Espèce supprimée');
    if (r !== undefined) { await refreshSpecies(); go('/liste'); }
  }

  function leave() {
    if (dirty && !confirm('Quitter sans enregistrer ?')) return;
    if (back) go(`/plante/${back}`);
    else go('/liste');
  }
</script>

{#if sp}
  <div class="page">
    <div class="row">
      <button class="ghost icon" aria-label="Retour" onclick={leave}>‹</button>
      <h1 class="grow">{CATEGORY_ICON[sp.category] || '🪴'} {sp.common_name}</h1>
    </div>

    {#if app.meta.ai_enabled}
      <button class="ai" disabled={aiBusy} onclick={askAI}>✨ {aiBusy ? "L'IA rédige la fiche…" : "Compléter avec l'IA"}</button>
    {/if}

    {#if ai}
      <section class="card proposals">
        <div class="row"><h2 class="grow">Propositions de l'IA</h2>
          {#if ai.confidence}<span class="pill ai">confiance {ai.confidence}</span>{/if}</div>
        {#if ai.note}<div class="notice small-text">{ai.note}</div>{/if}
        <p class="muted small-text">Vérifiez chaque valeur, en particulier la toxicité et les traitements. Les champs déjà remplis restent décochés.</p>
        <ul>
          {#each Object.entries(ai.proposals) as [k, v]}
            <li class:off={ai.decisions[k] !== 'accept'}>
              <label class="row tight">
                <input type="checkbox" checked={ai.decisions[k] === 'accept'} onchange={(e) => (ai.decisions[k] = e.currentTarget.checked ? 'accept' : 'reject')} />
                <span class="grow">
                  <strong>{labelOf(k)}</strong>
                  <span class="val">{show(k, v)}</span>
                  {#if current(k) != null}<span class="muted small-text">actuel : {show(k, current(k))}</span>{/if}
                </span>
              </label>
            </li>
          {/each}
        </ul>
        <div class="row">
          <button class="primary grow" onclick={applyAI}>Ajouter les champs cochés</button>
          <button class="small" onclick={() => Object.keys(ai.decisions).forEach((k) => (ai.decisions[k] = 'accept'))}>Tout cocher</button>
          <button class="ghost small" onclick={() => (ai = null)}>Ignorer</button>
        </div>
        <p class="muted small-text">Source : {ai.source}</p>
      </section>
    {/if}

    <section class="card">
      <h2>Identité</h2>
      <div class="grid2">
        <label class="field">Nom commun <input bind:value={sp.common_name} oninput={() => (dirty = true)} /></label>
        <label class="field">Cultivar / variété <input bind:value={sp.cultivar} oninput={() => (dirty = true)} /></label>
        <label class="field">Nom botanique {#if sp.attr_meta?.botanical_name}<span class="pill ai">IA</span>{/if}
          <input bind:value={sp.botanical_name} oninput={() => edited('botanical_name')} style="font-style: italic" /></label>
        <label class="field">Famille <input bind:value={sp.family} oninput={() => edited('family')} /></label>
        <label class="field">Catégorie
          <select bind:value={sp.category} onchange={() => edited('category')}>
            <option value={null}>—</option>
            {#each app.meta.categories as c}<option value={c.key}>{CATEGORY_ICON[c.key]} {c.label}</option>{/each}
          </select>
        </label>
      </div>
    </section>

    {#each sections as sec}
      <section class="card">
        <h2>{sec.name}</h2>
        <div class="grid2">
          {#each sec.fields as f (f.key)}
            <div oninput={() => edited(f.key)} onclick={(e) => e.target.closest('button') && edited(f.key)} role="presentation" class:wide={f.type === 'textarea' || f.type === 'months'}>
              <FieldInput field={f} bind:value={sp.attrs[f.key]} badge={sp.attr_meta?.[f.key]?.source} />
            </div>
          {/each}
        </div>
      </section>
    {/each}

    <section class="card">
      <h2>Spécimens de cette espèce ({specimens.length})</h2>
      {#each specimens as s}
        <button class="ghost line" onclick={() => go(`/plante/${s.id}`)}>{displayName(s)} ›</button>
      {:else}
        <p class="muted small-text">Aucun.</p>
      {/each}
      {#if !specimens.length}<button class="small danger" onclick={remove}>Supprimer cette espèce</button>{/if}
    </section>

    <div class="actions">
      <button class="ghost" onclick={leave}>Fermer</button>
      <button class="primary grow" disabled={!dirty || saving} onclick={() => save()}>{saving ? 'Enregistrement…' : dirty ? 'Enregistrer' : 'Enregistré'}</button>
    </div>
  </div>
{:else}
  <div class="page"><p class="muted">Chargement…</p></div>
{/if}

<style>
  .proposals { border-color: var(--ai); }
  .proposals ul { list-style: none; margin: 0; padding: 0; display: grid; gap: 4px; }
  .proposals li { padding: 8px 0; border-bottom: 1px solid var(--line); }
  .proposals li.off { opacity: 0.6; }
  .proposals input[type='checkbox'] { width: 22px; min-height: 22px; height: 22px; flex: none; accent-color: var(--ai); }
  .proposals .val { display: block; white-space: pre-line; }
  .tight { align-items: flex-start; flex-wrap: nowrap; }
  .wide { grid-column: 1 / -1; }
  .line { justify-content: flex-start; padding: 0; min-height: 40px; }
  .actions {
    position: sticky; bottom: 0; display: flex; gap: 10px; padding: 12px 0 calc(12px + env(safe-area-inset-bottom));
    background: linear-gradient(transparent, var(--bg) 30%);
  }
</style>
