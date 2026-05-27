<script lang="ts">
  import { onMount } from 'svelte';
  import { apiGet, apiPatch } from '$lib/api/client';
  import { displayValue } from '$lib/utils/format';
  import type { DeviceSetting } from '$lib/types/api';

  let settings = $state<DeviceSetting[]>([]);
  let values = $state<Record<string, string | number | boolean | null>>({});
  let error = $state('');
  let notice = $state('');
  let saving = $state(false);
  let showEditableOnly = $state(false);
  const visibleSettings = $derived(
    showEditableOnly ? settings.filter((setting) => setting.editable && setting.available) : settings
  );
  const groups = $derived(
    visibleSettings.reduce<Record<string, DeviceSetting[]>>((acc, setting) => {
      acc[setting.category] = [...(acc[setting.category] ?? []), setting];
      return acc;
    }, {})
  );

  onMount(async () => {
    await loadSettings();
  });

  async function loadSettings() {
    try {
      settings = await apiGet<DeviceSetting[]>('/device/settings');
      values = Object.fromEntries(settings.map((setting) => [setting.key, normalizeValue(setting.value)]));
    } catch (err) {
      error = err instanceof Error ? err.message : 'Device settings could not be loaded.';
    }
  }

  function normalizeValue(value: unknown) {
    if (typeof value === 'boolean' || typeof value === 'number' || typeof value === 'string') return value;
    if (value === null || value === undefined) return '';
    return String(value);
  }

  function changedValues() {
    const changes: Record<string, string | number | boolean | null> = {};
    for (const setting of settings) {
      if (!setting.editable || !setting.available) continue;
      const current = values[setting.key];
      const original = normalizeValue(setting.value);
      if (current === original || current === '') continue;
      if (setting.min_value !== null && Number(current) < setting.min_value) {
        throw new Error(`${setting.label} must be at least ${setting.min_value}.`);
      }
      if (setting.max_value !== null && Number(current) > setting.max_value) {
        throw new Error(`${setting.label} must be at most ${setting.max_value}.`);
      }
      changes[setting.key] = current;
    }
    return changes;
  }

  async function saveSettings() {
    error = '';
    notice = '';
    saving = true;
    try {
      const changes = changedValues();
      if (Object.keys(changes).length === 0) {
        notice = 'No changes to save.';
        return;
      }
      settings = await apiPatch<DeviceSetting[]>('/device/settings', { values: changes });
      values = Object.fromEntries(settings.map((setting) => [setting.key, normalizeValue(setting.value)]));
      notice = 'Settings saved.';
    } catch (err) {
      error = err instanceof Error ? err.message : 'Settings could not be saved.';
    } finally {
      saving = false;
    }
  }
</script>

<section class="page">
  <div class="page-header">
    <div>
      <h1>Device Settings</h1>
    </div>
    <div class="header-actions">
      <label class="editable-filter">
        <input type="checkbox" bind:checked={showEditableOnly} />
        <span>Editable only</span>
      </label>
      <button disabled={saving} onclick={saveSettings}>{saving ? 'Saving...' : 'Save Changes'}</button>
    </div>
  </div>

  {#if error}
    <div class="card">{error}</div>
  {:else}
    {#if visibleSettings.length === 0}
      <div class="card">No editable settings are available.</div>
    {:else}
      {#each Object.entries(groups) as [category, items]}
        <section class="card">
          <h2>{category}</h2>
          <div class="settings-grid">
            {#each items ?? [] as setting}
              <label>
                <span>{setting.label}</span>
                {#if setting.editable && setting.available && typeof setting.value === 'boolean'}
                  <input
                    type="checkbox"
                    checked={Boolean(values[setting.key])}
                    onchange={(event) => (values[setting.key] = event.currentTarget.checked)}
                  />
                {:else if setting.editable && setting.available && setting.options?.length}
                  <select bind:value={values[setting.key]}>
                    {#each setting.options as option}
                      <option value={option.value}>{option.label}</option>
                    {/each}
                  </select>
                {:else if setting.editable && setting.available}
                  <input
                    bind:value={values[setting.key]}
                    min={setting.min_value ?? undefined}
                    max={setting.max_value ?? undefined}
                  />
                {:else}
                  <input value={displayValue(setting.value, setting.unit ?? '')} disabled />
                {/if}
                {#if setting.options?.length}
                  <small>{setting.options.find((option) => option.value === values[setting.key])?.description ?? setting.description ?? (setting.available ? 'Editable' : 'Unavailable')}</small>
                {:else}
                  <small>{setting.description ?? (setting.available ? (setting.editable ? 'Editable' : 'Read-only') : 'Unavailable')}</small>
                {/if}
              </label>
            {/each}
          </div>
        </section>
      {/each}
    {/if}
    {#if notice}<div class="card">{notice}</div>{/if}
  {/if}
</section>

<style>
  h2 {
    margin: 0 0 1rem;
    font-size: 1.1rem;
  }

  .header-actions {
    display: flex;
    align-items: center;
    justify-content: end;
    gap: 0.75rem;
  }

  .editable-filter {
    display: inline-flex;
    align-items: center;
    min-height: 2.5rem;
    gap: 0.45rem;
    color: var(--muted);
    font-weight: 750;
  }

  .editable-filter input {
    min-height: auto;
  }

  .settings-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(15rem, 1fr));
    gap: 1rem;
  }

  label {
    display: grid;
    gap: 0.4rem;
    font-weight: 700;
  }

  small {
    color: var(--muted);
    font-weight: 500;
  }

  @media (max-width: 720px) {
    .header-actions {
      align-items: stretch;
      flex-direction: column;
      justify-content: start;
      width: 100%;
    }
  }
</style>
