<script>
  import { app, go, guard, refreshSpecimens, refreshSpecies } from '../lib/store.svelte.js';
  import { api } from '../lib/api.js';
  import { today, CATEGORY_ICON, fmtMeters } from '../lib/format.js';

  /** id : modification d'un spécimen ; query : création (lat, lon, acc, src venant de la carte). */
  let { id = null, query = {} } = $props();

  let loaded = $state(!id);
  let saving = $state(false);
  let f = $state({
    species_id: null, nickname: '', planted_on: '', age_years: '', age_estimated_on: today(), origin: '',
    status: 'en_place', exposure: '', soil: '', irrigation_zone: '', tags: '', notes: '',
  });
  let dateMode = $state('exact'); // exact | estimate | unknown
  let speciesQuery = $state('');
  let newCategory = $state('');
  let pickerOpen = $state(false);

  if (id) {
    api.get(`specimens/${id}`).then((s) => {
      Object.assign(f, {
        species_id: s.species_id, nickname: s.nickname || '', planted_on: s.planted_on || '',
        age_years: s.age_years ?? '', age_estimated_on: s.age_estimated_on || today(), origin: s.origin || '',
        status: s.status, exposure: s.exposure || '', soil: s.soil || '', irrigation_zone: s.irrigation_zone || '',
        tags: (s.tags || []).join(', '), notes: s.notes || '',
      });
      dateMode = s.planted_on ? 'exact' : s.age_years != null ? 'estimate' : 'unknown';
      speciesQuery = s.species ? speciesLabel(s.species) : '';
      loaded = true;
    });
  }

  function speciesLabel(sp) {
    return sp.common_name + (sp.cultivar ? ` ‘${sp.cultivar}’` : '');
  }

  let matches = $derived.by(() => {
    const q = speciesQuery.trim().toLowerCase();
    const list = q
      ? app.species.filter((s) => [s.common_name, s.botanical_name, s.cultivar].some((v) => v?.toLowerCase().includes(q)))
      : app.species;
    return list.slice(0, 8);
  });
  let exact = $derived(app.species.find((s) => speciesLabel(s).toLowerCase() === speciesQuery.trim().toLowerCase()));
  let selectedSpecies = $derived(app.species.find((s) => s.id === f.species_id));
  let creatingSpecies = $derived(!f.species_id && speciesQuery.trim() && !exact);
  let zones = $derived([...new Set(app.specimens.map((s) => s.irrigation_zone).filter(Boolean))]);

  function pick(sp) {
    f.species_id = sp.id;
    speciesQuery = speciesLabel(sp);
    pickerOpen = false;
  }

  function onSpeciesInput() {
    pickerOpen = true;
    if (selectedSpecies && speciesLabel(selectedSpecies) !== speciesQuery) f.species_id = null;
    if (exact) f.species_id = exact.id;
  }

  async function save(e) {
    e.preventDefault();
    if (!f.species_id && !speciesQuery.trim() && !f.nickname.trim()) return alert('Indiquez une espèce ou un nom.');
    saving = true;
    const result = await guard(async () => {
      let speciesId = f.species_id;
      if (creatingSpecies) {
        const sp = await api.post('species', { common_name: speciesQuery.trim(), category: newCategory || null });
        speciesId = sp.id;
        await refreshSpecies();
      }
      const body = {
        species_id: speciesId,
        nickname: f.nickname.trim() || null,
        planted_on: dateMode === 'exact' ? f.planted_on || null : null,
        age_years: dateMode === 'estimate' && f.age_years !== '' ? +f.age_years : null,
        age_estimated_on: dateMode === 'estimate' ? f.age_estimated_on || today() : null,
        origin: f.origin || null, status: f.status, exposure: f.exposure || null, soil: f.soil || null,
        irrigation_zone: f.irrigation_zone.trim() || null,
        tags: f.tags.split(',').map((t) => t.trim()).filter(Boolean),
        notes: f.notes || null,
      };
      if (id) return api.put(`specimens/${id}`, body);
      if (query.lat != null) {
        Object.assign(body, { lat: +query.lat, lon: +query.lon, gps_accuracy: query.acc ? +query.acc : null, position_source: query.src || 'manual' });
      }
      return api.post('specimens', body);
    }, id ? 'Fiche enregistrée' : 'Plante ajoutée');
    saving = false;
    if (result) {
      await refreshSpecimens();
      go(`/plante/${result.id}`, !id && creatingSpecies ? { nouvelle_espece: 1 } : undefined);
    }
  }

  function cancel() {
    if (id) go(`/plante/${id}`);
    else go('/');
  }
</script>

<form class="page" onsubmit={save}>
  <div class="row">
    <button type="button" class="ghost icon" aria-label="Retour" onclick={cancel}>‹</button>
    <h1 class="grow">{id ? 'Modifier la plante' : 'Nouvelle plante'}</h1>
  </div>

  {#if !id && query.lat != null}
    <div class="notice info small-text">
      Position enregistrée sur la carte{#if query.acc} (GPS ±{fmtMeters(+query.acc)}){:else if query.src === 'manual'} (placée à la main){/if}.
    </div>
  {/if}

  {#if loaded}
    <section class="card">
      <h2>Identité</h2>
      <div class="combo">
        <label class="field">Espèce
          <input placeholder="Rechercher ou saisir un nom (ex. Figuier)" bind:value={speciesQuery} oninput={onSpeciesInput}
            onfocus={() => (pickerOpen = true)} onblur={() => setTimeout(() => (pickerOpen = false), 180)} autocomplete="off" />
        </label>
        {#if pickerOpen && matches.length && !(selectedSpecies && speciesLabel(selectedSpecies) === speciesQuery)}
          <ul class="options" role="listbox">
            {#each matches as sp}
              <li><button type="button" onmousedown={(e) => e.preventDefault()} onclick={() => pick(sp)}>
                <span>{CATEGORY_ICON[sp.category] || '🪴'}</span>
                <span class="grow">{speciesLabel(sp)} {#if sp.botanical_name}<em class="muted">{sp.botanical_name}</em>{/if}</span>
                <span class="muted small-text">{sp.specimen_count}</span>
              </button></li>
            {/each}
          </ul>
        {/if}
      </div>
      {#if creatingSpecies}
        <div class="notice info small-text">
          Nouvelle espèce « {speciesQuery.trim()} ». Vous pourrez compléter sa fiche ensuite (à la main ou avec l'IA).
          <label class="field">Catégorie
            <select bind:value={newCategory}>
              <option value="">—</option>
              {#each app.meta.categories as c}<option value={c.key}>{CATEGORY_ICON[c.key]} {c.label}</option>{/each}
            </select>
          </label>
        </div>
      {/if}
      <label class="field">Surnom <span class="hint">facultatif, pour distinguer plusieurs sujets (« Cerisier du fond »)</span>
        <input bind:value={f.nickname} />
      </label>
    </section>

    <section class="card">
      <h2>Âge</h2>
      <div class="chips">
        <button type="button" class="chip" class:on={dateMode === 'exact'} onclick={() => (dateMode = 'exact')}>Date de plantation</button>
        <button type="button" class="chip" class:on={dateMode === 'estimate'} onclick={() => (dateMode = 'estimate')}>Âge estimé</button>
        <button type="button" class="chip" class:on={dateMode === 'unknown'} onclick={() => (dateMode = 'unknown')}>Inconnu</button>
      </div>
      {#if dateMode === 'exact'}
        <label class="field">Plantée le <input type="date" bind:value={f.planted_on} max={today()} /></label>
      {:else if dateMode === 'estimate'}
        <div class="grid2">
          <label class="field">Âge estimé (ans) <input type="number" min="0" step="0.5" inputmode="decimal" bind:value={f.age_years} /></label>
          <label class="field">Estimé le <input type="date" bind:value={f.age_estimated_on} max={today()} /></label>
        </div>
        <p class="muted small-text">L'âge affiché augmentera tout seul avec le temps.</p>
      {/if}
      <div class="grid2">
        <label class="field">Origine
          <select bind:value={f.origin}><option value="">—</option>{#each app.meta.origins as o}<option>{o}</option>{/each}</select>
        </label>
        <label class="field">Statut
          <select bind:value={f.status}>{#each app.meta.statuses as s}<option value={s.key}>{s.label}</option>{/each}</select>
        </label>
      </div>
    </section>

    <section class="card">
      <h2>Conditions à cet endroit</h2>
      <div class="grid2">
        <label class="field">Exposition constatée
          <select bind:value={f.exposure}><option value="">—</option>{#each app.meta.exposures as o}<option>{o}</option>{/each}</select>
        </label>
        <label class="field">Sol constaté <input bind:value={f.soil} placeholder="argileux, sableux…" /></label>
        <label class="field">Zone d'arrosage
          <input bind:value={f.irrigation_zone} list="zones" placeholder="ex. Potager" />
          <datalist id="zones">{#each zones as z}<option value={z}></option>{/each}</datalist>
        </label>
        <label class="field">Étiquettes <span class="hint">séparées par des virgules</span><input bind:value={f.tags} placeholder="verger, haie nord" /></label>
      </div>
      <label class="field">Notes <textarea bind:value={f.notes}></textarea></label>
    </section>

    <div class="actions">
      <button type="button" class="ghost" onclick={cancel}>Annuler</button>
      <button type="submit" class="primary grow" disabled={saving}>{saving ? 'Enregistrement…' : 'Enregistrer'}</button>
    </div>
  {:else}
    <p class="muted">Chargement…</p>
  {/if}
</form>

<style>
  .combo { position: relative; }
  .options {
    position: absolute; left: 0; right: 0; top: 100%; z-index: 20; margin: 4px 0 0; padding: 4px; list-style: none;
    background: var(--surface); border: 1px solid var(--line); border-radius: 12px; box-shadow: var(--shadow); max-height: 320px; overflow-y: auto;
  }
  .options button { width: 100%; justify-content: flex-start; border: 0; border-radius: 8px; font-weight: 500; text-align: left; white-space: normal; }
  .options button:hover { background: var(--leaf-soft); }
  .actions {
    position: sticky; bottom: 0; display: flex; gap: 10px; padding: 12px 0 calc(12px + env(safe-area-inset-bottom));
    background: linear-gradient(transparent, var(--bg) 30%);
  }
</style>
