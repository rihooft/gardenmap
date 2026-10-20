<script>
  import { MONTHS_SHORT, MONTHS } from '../lib/format.js';

  /** Champ de fiche espèce selon son type (catalogue servi par /api/meta). */
  let { field, value = $bindable(), badge = null } = $props();

  function toggleMonth(m) {
    const cur = new Set(value || []);
    cur.has(m) ? cur.delete(m) : cur.add(m);
    value = cur.size ? [...cur].sort((a, b) => a - b) : null;
  }

  function toggleOption(o) {
    const cur = new Set(value || []);
    cur.has(o) ? cur.delete(o) : cur.add(o);
    value = cur.size ? field.options.filter((x) => cur.has(x)) : null;
  }
</script>

<div class="fi" class:wide={field.type === 'textarea' || field.type === 'months'}>
  <div class="lbl">
    <span>{field.label}{field.unit ? ` (${field.unit})` : ''}</span>
    {#if badge}<span class="pill ai" title={badge}>IA</span>{/if}
  </div>
  {#if field.type === 'textarea'}
    <textarea bind:value rows="3"></textarea>
  {:else if field.type === 'number'}
    <input type="number" step="any" inputmode="decimal" value={value ?? ''} oninput={(e) => (value = e.currentTarget.value === '' ? null : +e.currentTarget.value)} />
  {:else if field.type === 'select'}
    <select value={value ?? ''} onchange={(e) => (value = e.currentTarget.value || null)}>
      <option value="">—</option>
      {#each field.options as o}<option value={o}>{o}</option>{/each}
    </select>
  {:else if field.type === 'multi'}
    <div class="chips wrap">
      {#each field.options as o}
        <button type="button" class="chip" class:on={value?.includes(o)} aria-pressed={!!value?.includes(o)} onclick={() => toggleOption(o)}>{o}</button>
      {/each}
    </div>
  {:else if field.type === 'months'}
    <div class="months" role="group" aria-label={field.label}>
      {#each MONTHS_SHORT as m, i}
        <button type="button" class:on={value?.includes(i + 1)} aria-pressed={!!value?.includes(i + 1)} title={MONTHS.at(i)} onclick={() => toggleMonth(i + 1)}>{m}</button>
      {/each}
    </div>
  {:else if field.type === 'bool'}
    <div class="chips">
      <button type="button" class="chip" class:on={value === true} onclick={() => (value = value === true ? null : true)}>Oui</button>
      <button type="button" class="chip" class:on={value === false} onclick={() => (value = value === false ? null : false)}>Non</button>
    </div>
  {:else}
    <input type="text" value={value ?? ''} oninput={(e) => (value = e.currentTarget.value || null)} />
  {/if}
</div>

<style>
  .fi { display: grid; gap: 6px; align-content: start; }
  .fi.wide { grid-column: 1 / -1; }
  .lbl { display: flex; gap: 8px; align-items: center; font-size: 0.9rem; color: var(--ink-2); font-weight: 600; }
  .wrap { flex-wrap: wrap; }
  .months { display: grid; grid-template-columns: repeat(12, 1fr); gap: 3px; }
  .months button { min-height: 40px; padding: 0; border-radius: 8px; font-size: 0.85rem; }
  .months button.on { background: var(--leaf); color: #fff; border-color: var(--leaf); }
</style>
