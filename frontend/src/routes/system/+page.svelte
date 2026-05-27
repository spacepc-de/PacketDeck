<script lang="ts">
  import { onMount } from 'svelte';
  import { apiGet, apiPatch, apiPost } from '$lib/api/client';
  import type { ApiEvent, ConnectionStatus } from '$lib/types/api';
  import StatusPill from '$lib/components/StatusPill.svelte';

  let connection = $state<ConnectionStatus | null>(null);
  let events = $state<ApiEvent[]>([]);
  let retention = $state({
    telemetry_retention_days: 30,
    node_retention_days: 90,
    telemetry_poll_interval_seconds: 30,
    favorite_node_telemetry_enabled: true,
    favorite_node_telemetry_interval_seconds: 300
  });
  let windowSeconds = $state(300);
  let limit = $state(200);
  let source = $state('');
  let autoRefresh = $state(true);
  let error = $state('');
  let loading = $state(false);
  let settingsState = $state<'idle' | 'saving' | 'saved' | 'error'>('idle');
  let settingsMessage = $state('');
  let refreshTimer: ReturnType<typeof setInterval> | null = null;

  onMount(() => {
    refreshAll();
    refreshTimer = setInterval(() => {
      if (autoRefresh) refreshEvents();
    }, 3000);
    return () => {
      if (refreshTimer) clearInterval(refreshTimer);
    };
  });

  async function refreshAll() {
    const settings = await apiGet<{ retention: typeof retention }>('/system/settings');
    retention = settings.retention;
    connection = await apiGet<ConnectionStatus>('/connection/status');
    await refreshEvents();
  }

  async function saveSettings() {
    settingsState = 'saving';
    settingsMessage = '';
    try {
      const result = await apiPatch<{ retention: typeof retention; cleanup: Record<string, number> }>('/system/settings', {
        retention
      });
      retention = result.retention;
      settingsState = 'saved';
      settingsMessage = `Retention saved. Removed ${result.cleanup.gateway_telemetry_deleted} gateway records, ${result.cleanup.node_telemetry_deleted} node telemetry records, and ${result.cleanup.nodes_deleted} stale nodes.`;
      await refreshEvents();
    } catch (err) {
      settingsState = 'error';
      settingsMessage = err instanceof Error ? err.message : 'Settings could not be saved.';
    }
  }

  async function applyRetentionNow() {
    settingsState = 'saving';
    try {
      const cleanup = await apiPost<Record<string, number>>('/system/retention/apply');
      settingsState = 'saved';
      settingsMessage = `Cleanup complete. Removed ${cleanup.gateway_telemetry_deleted} gateway records, ${cleanup.node_telemetry_deleted} node telemetry records, and ${cleanup.nodes_deleted} stale nodes.`;
    } catch (err) {
      settingsState = 'error';
      settingsMessage = err instanceof Error ? err.message : 'Retention cleanup failed.';
    }
  }

  async function refreshEvents() {
    loading = true;
    error = '';
    try {
      const params = new URLSearchParams({
        window_seconds: String(windowSeconds),
        limit: String(limit)
      });
      if (source) params.set('source', source);
      events = await apiGet<ApiEvent[]>(`/system/events?${params.toString()}`);
    } catch (err) {
      error = err instanceof Error ? err.message : 'System events could not be loaded.';
    } finally {
      loading = false;
    }
  }

  function eventPayload(event: ApiEvent) {
    return JSON.stringify(event.payload, null, 2);
  }

  function eventTime(value: string) {
    return new Intl.DateTimeFormat('en', { timeStyle: 'medium' }).format(new Date(value));
  }
</script>

<section class="page">
  <div class="page-header">
    <div>
      <h1>System</h1>
      <p class="muted">Runtime versions, diagnostics, database status, MQTT status, and system events.</p>
    </div>
  </div>

  <div class="grid">
    <div class="card">
      <div class="metric-label">Backend version</div>
      <div class="metric-value">0.1.0</div>
    </div>
    <div class="card">
      <div class="metric-label">Frontend version</div>
      <div class="metric-value">0.1.0</div>
    </div>
    <div class="card">
      <div class="metric-label">MeshCore library</div>
      <div class="metric-value">{connection?.api_library_version ?? 'Unavailable'}</div>
    </div>
    <div class="card">
      <div class="metric-label">Connection</div>
      {#if connection}<StatusPill status={connection.state} />{/if}
    </div>
  </div>

  <section class="card">
    <div class="settings-header">
      <div>
        <h2>System Settings</h2>
        <p class="muted">Control telemetry history retention, node expiry, gateway polling, and favorite node telemetry polling.</p>
      </div>
      <div class="settings-actions">
        <button class="secondary" onclick={applyRetentionNow} disabled={settingsState === 'saving'}>Apply cleanup</button>
        <button onclick={saveSettings} disabled={settingsState === 'saving'}>{settingsState === 'saving' ? 'Saving...' : 'Save settings'}</button>
      </div>
    </div>

    <div class="settings-grid">
      <label>
        <span>Telemetry retention</span>
        <input type="number" min="1" max="3650" bind:value={retention.telemetry_retention_days} />
        <small>Days to keep gateway and node telemetry history.</small>
      </label>
      <label>
        <span>Node retention</span>
        <input type="number" min="1" max="3650" bind:value={retention.node_retention_days} />
        <small>Days after last heard before a node is removed.</small>
      </label>
      <label>
        <span>Telemetry polling interval</span>
        <input type="number" min="5" max="3600" bind:value={retention.telemetry_poll_interval_seconds} />
        <small>Seconds between automatic gateway telemetry snapshots.</small>
      </label>
      <label class="toggle-setting">
        <span>Favorite node telemetry</span>
        <input type="checkbox" bind:checked={retention.favorite_node_telemetry_enabled} />
        <small>Automatically refresh telemetry for favorite nodes.</small>
      </label>
      <label>
        <span>Favorite telemetry interval</span>
        <input type="number" min="30" max="86400" bind:value={retention.favorite_node_telemetry_interval_seconds} />
        <small>Seconds between automatic telemetry requests for favorite nodes.</small>
      </label>
    </div>

    {#if settingsMessage}
      <p class:error={settingsState === 'error'} class="muted">{settingsMessage}</p>
    {/if}
  </section>

  <section class="card">
    <div class="logs-header">
      <div>
        <h2>Logs and Events</h2>
        <p class="muted">Rolling event buffer from the application, API, WebSocket stream, and MeshCore device.</p>
      </div>
      <div class="controls">
        <select bind:value={windowSeconds} onchange={refreshEvents} aria-label="Rolling window">
          <option value={60}>Last minute</option>
          <option value={300}>Last 5 minutes</option>
          <option value={900}>Last 15 minutes</option>
          <option value={3600}>Last hour</option>
          <option value={21600}>Last 6 hours</option>
          <option value={86400}>Last 24 hours</option>
        </select>
        <select bind:value={limit} onchange={refreshEvents} aria-label="Event limit">
          <option value={50}>50 events</option>
          <option value={100}>100 events</option>
          <option value={200}>200 events</option>
          <option value={500}>500 events</option>
          <option value={1000}>1000 events</option>
        </select>
        <select bind:value={source} onchange={refreshEvents} aria-label="Event source">
          <option value="">All sources</option>
          <option value="app">Application</option>
          <option value="meshcore">MeshCore</option>
        </select>
        <label class="toggle">
          <input type="checkbox" bind:checked={autoRefresh} />
          <span>Auto refresh</span>
        </label>
        <button class="secondary" onclick={refreshEvents} disabled={loading}>
          {loading ? 'Refreshing...' : 'Refresh'}
        </button>
      </div>
    </div>

    {#if error}
      <p class="error">{error}</p>
    {:else if events.length === 0}
      <p class="muted">No events are available for the selected window.</p>
    {:else}
      <div class="event-table">
        <table>
          <thead>
            <tr>
              <th>Time</th>
              <th>Source</th>
              <th>Severity</th>
              <th>Type</th>
              <th>Payload</th>
            </tr>
          </thead>
          <tbody>
            {#each [...events].reverse() as event}
              <tr>
                <td>{eventTime(event.created_at)}</td>
                <td><StatusPill status={event.source ?? 'app'} /></td>
                <td><StatusPill status={event.severity ?? 'info'} /></td>
                <td class="event-type">{event.type}</td>
                <td><pre>{eventPayload(event)}</pre></td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {/if}
  </section>
</section>

<style>
  h2 {
    margin: 0 0 0.75rem;
  }

  .logs-header {
    display: grid;
    gap: 1rem;
  }

  .settings-header {
    display: flex;
    justify-content: space-between;
    gap: 1rem;
    align-items: start;
  }

  .settings-actions {
    display: flex;
    flex-wrap: wrap;
    gap: 0.75rem;
    justify-content: end;
  }

  .settings-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(14rem, 1fr));
    gap: 1rem;
    margin-top: 1rem;
  }

  .settings-grid label {
    display: grid;
    gap: 0.4rem;
    font-weight: 700;
  }

  .settings-grid small {
    color: var(--muted);
    font-weight: 500;
  }

  .toggle-setting input {
    justify-self: start;
    min-height: auto;
  }

  .controls {
    display: flex;
    flex-wrap: wrap;
    gap: 0.75rem;
    align-items: center;
  }

  .toggle {
    display: inline-flex;
    align-items: center;
    gap: 0.45rem;
    min-height: 2.5rem;
    color: var(--muted);
    font-weight: 700;
  }

  .toggle input {
    min-height: auto;
  }

  .event-table {
    overflow-x: auto;
  }

  .event-type {
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    font-size: 0.85rem;
    white-space: nowrap;
  }

  pre {
    max-width: 42rem;
    max-height: 12rem;
    overflow: auto;
    margin: 0;
    white-space: pre-wrap;
    word-break: break-word;
    font-size: 0.78rem;
  }

  .error {
    color: #fecdd3;
  }
</style>
