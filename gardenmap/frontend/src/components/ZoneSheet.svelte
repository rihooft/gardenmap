<script>
  import { app } from '../lib/store.svelte.js';
  import { fmtMeasure } from '../lib/geomap.js';

  /**
   * zone : { id?, kind, name, notes } ; geom : 'polygon' | 'line' ; measure : { area_m2 | length_m }
   * shapeEditing : sommets en cours de modification
   */
  let { zone, geom, measure, shapeEditing = false, onsave, oncancel, ondelete, onshape, values = $bindable() } = $props();

  let kind = $state(zone.kind || (geom === 'line' ? 'mur' : null));
  let name = $state(zone.name || '');
  let notes = $state(zone.notes || '');
  let kinds = $derived(app.meta.zone_kinds.filter((k) => k.geom === geom));
  let isNew = !zone.id;
  let showNotes = $state(!!zone.notes);

  // valeurs en cours, lues par la carte si l'on quitte le mode aplats sans passer par « Enregistrer »
  $effect(() => {
    values = { kind, name: name.trim() || null, notes: notes.trim() || null };
  });
</script>

<div class="sheet" class:compact={shapeEditing} role="dialog" aria-label="Zone">
  {#if shapeEditing}
    <div class="row">
      <span class="grow small-text">Glissez les sommets ; touchez le milieu d'un côté pour en ajouter un, un sommet pour le retirer.</span>
      {#if measure}<span class="pill">{fmtMeasure(measure)}</span>{/if}
    </div>
    <div class="row">
      <button class="primary grow" onclick={() => onsave({ kind, name: name.trim() || null, notes: notes.trim() || null })}>Enregistrer</button>
      <button class="small" onclick={() => onshape()}>Fin de la forme</button>
      <button class="ghost small" onclick={() => oncancel()}>Annuler la modification</button>
    </div>
  {:else}
    <div class="row">
      <h2 class="grow">{isNew ? (geom === 'line' ? 'Nouvelle ligne' : 'Nouvelle surface') : name || app.meta.zone_kinds.find((k) => k.key === zone.kind)?.label}</h2>
      {#if measure}<span class="pill">{fmtMeasure(measure)}</span>{/if}
    </div>

    <div class="kinds" role="radiogroup" aria-label="Type de zone">
      {#each kinds as k}
        <button class="kind" class:on={kind === k.key} role="radio" aria-checked={kind === k.key} onclick={() => (kind = k.key)}>
          <span class="sw" style="background:{k.color}" class:line={k.geom === 'line'}></span>{k.label}
        </button>
      {/each}
    </div>

    <input aria-label="Nom de la zone" bind:value={name} placeholder={geom === 'line' ? 'Nom (facultatif) : mur du fond' : 'Nom (facultatif) : massif de la terrasse'} />
    {#if showNotes}
      <textarea aria-label="Notes" bind:value={notes} rows="2" placeholder="Notes"></textarea>
    {:else}
      <button class="link small-text" onclick={() => (showNotes = true)}>＋ Ajouter une note</button>
    {/if}

    <div class="row">
      <button class="primary grow" disabled={!kind} onclick={() => onsave({ kind, name: name.trim() || null, notes: notes.trim() || null })}>
        {isNew ? 'Ajouter' : 'Enregistrer'}
      </button>
      {#if !isNew && onshape}<button class="small" onclick={() => onshape()}>✏️ Forme</button>{/if}
      {#if !isNew && ondelete}<button class="small danger" aria-label="Supprimer la zone" onclick={() => ondelete()}>🗑</button>{/if}
      <button class="ghost small" onclick={() => oncancel()}>Annuler</button>
    </div>
  {/if}
</div>

<style>
  .sheet {
    position: absolute; left: 12px; right: 12px; bottom: 12px; z-index: 1000; max-width: 560px; margin: 0 auto;
    background: var(--surface); border-radius: 18px; box-shadow: var(--shadow); padding: 14px 16px; display: grid; gap: 10px;
  }
  .sheet.compact { padding: 10px 12px; gap: 8px; }
  .kinds { display: flex; gap: 6px; overflow-x: auto; padding-bottom: 4px; margin: 0 -4px; padding-left: 4px; scrollbar-width: thin; }
  .kind { flex: none; min-height: 38px; padding: 0 12px 0 8px; font-size: 0.86rem; font-weight: 600; gap: 6px; }
  .kind.on { border-color: var(--forest); box-shadow: 0 0 0 2px var(--forest) inset; background: var(--leaf-soft); }
  .sw { width: 18px; height: 18px; border-radius: 5px; border: 1px solid rgb(0 0 0 / 0.2); flex: none; }
  .sw.line { height: 5px; border-radius: 2px; }
  .link { justify-self: start; border: 0; background: none; min-height: 28px; padding: 0; color: var(--leaf); }
</style>
