<script>
  import { BASES, PRESETS } from '../lib/geomap.js';

  /** prefs : préférences d'affichage (objet réactif modifié en place) ; onchange() ; onclose() */
  let { prefs, onchange, onclose } = $props();

  const presetLabels = { photo: 'Photo seule', mixte: 'Photo + aplats', plan: 'Plan simplifié' };

  function preset(key) {
    Object.assign(prefs, PRESETS[key], { preset: key });
    onchange();
  }

  function set(k, v) {
    prefs[k] = v;
    prefs.preset = null;
    onchange();
  }
</script>

<div class="sheet" role="dialog" aria-label="Affichage de la carte">
  <div class="row"><h2 class="grow">Affichage</h2><button class="ghost small" aria-label="Fermer" onclick={() => onclose()}>✕</button></div>

  <div class="presets">
    {#each Object.keys(PRESETS) as k}
      <button class="preset" class:on={prefs.preset === k} onclick={() => preset(k)}>
        <span class="thumb t-{k}" aria-hidden="true"></span>{presetLabels[k]}
      </button>
    {/each}
  </div>

  <h3>Fond de carte</h3>
  <div class="chips">
    {#each Object.entries(BASES) as [k, b]}
      <button class="chip" class:on={prefs.base === k} onclick={() => set('base', k)}>{b.label}</button>
    {/each}
  </div>
  {#if prefs.base !== 'none'}
    <label class="field">Intensité du fond · {Math.round(prefs.photoOpacity * 100)} %
      <input type="range" min="0.1" max="1" step="0.05" value={prefs.photoOpacity} oninput={(e) => set('photoOpacity', +e.currentTarget.value)} />
    </label>
  {/if}

  <h3>Aplats</h3>
  <div class="chips">
    <button class="chip" class:on={prefs.zones} onclick={() => set('zones', !prefs.zones)}>{prefs.zones ? 'Affichés' : 'Masqués'}</button>
    <button class="chip" class:on={prefs.labels} onclick={() => set('labels', !prefs.labels)}>Noms des zones</button>
  </div>
  {#if prefs.zones}
    <label class="field">Opacité des aplats · {Math.round(prefs.zonesOpacity * 100)} %
      <input type="range" min="0.15" max="1" step="0.05" value={prefs.zonesOpacity} oninput={(e) => set('zonesOpacity', +e.currentTarget.value)} />
    </label>
  {/if}

  <h3>Repères</h3>
  <div class="chips">
    <button class="chip" class:on={prefs.cadastre} onclick={() => set('cadastre', !prefs.cadastre)}>Limites cadastrales</button>
  </div>
  <p class="muted small-text">Fonds et cadastre : IGN, Géoplateforme (licence ouverte Etalab 2.0).</p>
</div>

<style>
  .sheet {
    position: absolute; left: 12px; right: 12px; bottom: 12px; z-index: 1000; max-width: 520px; margin: 0 auto;
    background: var(--surface); border-radius: 18px; box-shadow: var(--shadow); padding: 16px 18px; display: grid; gap: 10px;
    max-height: calc(100% - 24px); overflow-y: auto;
  }
  .presets { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
  .preset { flex-direction: column; min-height: 0; padding: 8px 4px; border-radius: 14px; gap: 6px; font-size: 0.82rem; white-space: normal; text-align: center; }
  .preset.on { border-color: var(--forest); box-shadow: 0 0 0 2px var(--forest) inset; }
  .thumb { width: 100%; aspect-ratio: 16 / 10; border-radius: 8px; display: block; }
  .t-photo { background: linear-gradient(135deg, #3d5e35, #6d8f55 40%, #4f6f43 60%, #8a8578); }
  .t-mixte { background: linear-gradient(135deg, rgb(168 207 111 / 0.8) 0 45%, rgb(95 182 230 / 0.8) 45% 60%, rgb(181 174 166 / 0.85) 60%), linear-gradient(135deg, #3d5e35, #8a8578); }
  .t-plan { background: linear-gradient(135deg, #a8cf6f 0 45%, #5fb6e6 45% 60%, #b5aea6 60%); }
  h3 { margin-top: 4px; }
  input[type='range'] { padding: 0; min-height: 32px; accent-color: var(--forest); }
</style>
