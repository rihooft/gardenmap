<script>
  import { onDestroy } from 'svelte';
  import { startAveraging, explainGeoError, geolocationAvailable, inIframe } from '../lib/gps.js';
  import { api } from '../lib/api.js';
  import { app } from '../lib/store.svelte.js';
  import { fmtMeters } from '../lib/format.js';

  /** onresult({lat, lon, accuracy, source}) · onmanual() · oncancel() */
  let { onresult, onmanual, oncancel, title = 'Mesure de votre position', maxSeconds = 30 } = $props();

  let state = $state(geolocationAvailable() ? 'measuring' : 'error');
  let fix = $state(null);
  let error = $state(geolocationAvailable() ? null : explainGeoError(null));
  let session = null;
  let timer;

  function finish() {
    const r = session?.result();
    session?.stop();
    clearTimeout(timer);
    if (r) onresult({ lat: r.lat, lon: r.lon, accuracy: r.accuracy, source: 'gps' });
  }

  if (state === 'measuring') {
    session = startAveraging({
      onUpdate: (u) => (fix = u),
      onError: (err) => {
        if (fix) return; // une erreur ponctuelle après un premier point n'arrête pas la mesure
        session?.stop();
        state = 'error';
        error = explainGeoError(err);
      },
    });
    timer = setTimeout(finish, maxSeconds * 1000);
  }

  onDestroy(() => {
    session?.stop();
    clearTimeout(timer);
  });

  let trackerBusy = $state(false);
  async function useTracker() {
    trackerBusy = true;
    try {
      const t = await api.get('ha/position');
      session?.stop();
      onresult({ lat: t.lat, lon: t.lon, accuracy: t.accuracy ?? 20, source: 'tracker' });
    } catch (e) {
      error = e.message;
      state = 'error';
    } finally {
      trackerBusy = false;
    }
  }

  let progress = $derived(fix ? Math.min(1, fix.elapsed / maxSeconds) : 0);
</script>

<div class="sheet" role="dialog" aria-label={title}>
  <h2>{title}</h2>
  {#if state === 'measuring'}
    {#if !fix}
      <p class="muted">Recherche du signal GPS… Restez immobile au pied de la plante.</p>
    {:else}
      <div class="stats">
        <div><strong>±{fmtMeters(fix.accuracy)}</strong><span>précision estimée</span></div>
        <div><strong>{fix.count}</strong><span>mesure{fix.count > 1 ? 's' : ''}</span></div>
        <div><strong>±{fmtMeters(fix.last.accuracy)}</strong><span>dernière mesure</span></div>
      </div>
      <div class="bar"><span style="width:{progress * 100}%"></span></div>
      <p class="muted small-text">La précision s'améliore en restant immobile quelques secondes.</p>
    {/if}
    <div class="row">
      <button class="primary grow" disabled={!fix} onclick={finish}>Utiliser cette position</button>
      <button class="ghost" onclick={() => { session?.stop(); oncancel?.(); }}>Annuler</button>
    </div>
  {:else}
    <div class="notice">{error}</div>
    <div class="actions">
      {#if inIframe}
        <button onclick={() => window.open(location.href, '_blank')}>↗ Ouvrir en plein écran</button>
      {/if}
      {#if app.meta?.tracker_entity}
        <button disabled={trackerBusy} onclick={useTracker}>📱 Position de l'app Home Assistant</button>
      {/if}
      {#if onmanual}<button onclick={() => onmanual()}>✋ Placer à la main</button>{/if}
      <button class="ghost" onclick={() => oncancel?.()}>Annuler</button>
    </div>
  {/if}
</div>

<style>
  .sheet {
    position: absolute; left: 12px; right: 12px; bottom: 12px; z-index: 1000;
    background: var(--surface); border-radius: 18px; box-shadow: var(--shadow); padding: 18px; display: grid; gap: 14px;
    max-width: 520px; margin: 0 auto;
  }
  .stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; text-align: center; }
  .stats div { display: grid; }
  .stats strong { font-size: 1.3rem; color: var(--forest); }
  .stats span { font-size: 0.78rem; color: var(--ink-2); }
  .bar { height: 6px; border-radius: 3px; background: var(--surface-2); overflow: hidden; }
  .bar span { display: block; height: 100%; background: var(--leaf); transition: width 0.5s; }
  .actions { display: grid; gap: 8px; }
</style>
