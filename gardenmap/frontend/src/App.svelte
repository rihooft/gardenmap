<script>
  import { app, route, loadAll, go } from './lib/store.svelte.js';
  import { inIframe } from './lib/gps.js';
  import MapView from './views/MapView.svelte';
  import ListView from './views/ListView.svelte';
  import SpecimenView from './views/SpecimenView.svelte';
  import SpecimenForm from './views/SpecimenForm.svelte';
  import SpeciesView from './views/SpeciesView.svelte';
  import SettingsView from './views/SettingsView.svelte';

  loadAll();

  const tabs = [
    { path: '/', label: 'Plan', icon: '🗺️' },
    { path: '/liste', label: 'Plantes', icon: '🌿' },
    { path: '/reglages', label: 'Réglages', icon: '⚙️' },
  ];

  let mainEl = $state();
  $effect(() => {
    route.path;
    if (mainEl) mainEl.scrollTop = 0;
  });

  let segments = $derived(route.path.split('/').filter(Boolean));
  let tab = $derived(segments[0] === 'liste' || segments[0] === 'plante' || segments[0] === 'espece' ? '/liste' : segments[0] === 'reglages' ? '/reglages' : '/');
</script>

<div class="shell">
  <main bind:this={mainEl}>
    {#if app.loading}
      <div class="center muted">Chargement du jardin…</div>
    {:else if app.error}
      <div class="page"><div class="notice">Impossible de joindre le serveur GardenMap : {app.error}</div></div>
    {:else if route.path === '/' }
      <MapView />
    {:else if segments[0] === 'liste'}
      <ListView />
    {:else if segments[0] === 'nouvelle'}
      <SpecimenForm query={route.query} />
    {:else if segments[0] === 'plante' && segments[2] === 'modifier'}
      {#key segments[1]}<SpecimenForm id={+segments[1]} />{/key}
    {:else if segments[0] === 'plante'}
      {#key segments[1]}<SpecimenView id={+segments[1]} />{/key}
    {:else if segments[0] === 'espece'}
      {#key segments[1]}<SpeciesView id={+segments[1]} back={route.query.retour} />{/key}
    {:else if segments[0] === 'reglages'}
      <SettingsView />
    {:else}
      <div class="page"><p>Page introuvable.</p><button onclick={() => go('/')}>Retour au plan</button></div>
    {/if}
  </main>

  <nav class="tabs" aria-label="Navigation">
    {#each tabs as t}
      <button class="tab" class:on={tab === t.path} onclick={() => go(t.path)} aria-current={tab === t.path ? 'page' : undefined}>
        <span class="ti" aria-hidden="true">{t.icon}</span><span>{t.label}</span>
      </button>
    {/each}
    {#if inIframe}
      <button class="tab" title="Ouvrir en plein écran (nécessaire pour le GPS sur certains téléphones)" onclick={() => window.open(location.href, '_blank')}>
        <span class="ti" aria-hidden="true">↗</span><span>Plein écran</span>
      </button>
    {/if}
  </nav>

  {#if app.toast}
    <div class="toast" class:error={app.toast.kind === 'error'} role="status">{app.toast.message}</div>
  {/if}
</div>

<style>
  .shell { height: 100%; display: grid; grid-template-rows: 1fr auto; }
  main { overflow-y: auto; position: relative; min-height: 0; }
  .center { height: 100%; display: grid; place-items: center; }
  .tabs {
    display: flex; justify-content: space-around; gap: 4px;
    background: var(--surface); border-top: 1px solid var(--line);
    padding: 4px 8px calc(4px + env(safe-area-inset-bottom));
  }
  .tab { flex: 1; max-width: 160px; flex-direction: column; gap: 0; min-height: 54px; border: 0; background: none; border-radius: 12px; font-size: 0.78rem; color: var(--ink-2); padding: 0; }
  .tab .ti { font-size: 1.25rem; line-height: 1.3; }
  .tab.on { color: var(--forest); background: var(--leaf-soft); }
  .toast {
    position: fixed; left: 50%; bottom: calc(80px + env(safe-area-inset-bottom)); transform: translateX(-50%);
    background: var(--forest); color: var(--surface); padding: 12px 18px; border-radius: 12px; box-shadow: var(--shadow);
    z-index: 2000; max-width: calc(100vw - 32px); font-weight: 600;
  }
  .toast.error { background: var(--danger); color: #fff; }
</style>
