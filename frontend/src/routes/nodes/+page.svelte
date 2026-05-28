<script lang="ts">
  import { onMount } from 'svelte';
  import StatusPill from '$lib/components/StatusPill.svelte';
  import MetricChart from '$lib/components/MetricChart.svelte';
  import { apiDelete, apiGet, apiPatch, apiPost, apiPut } from '$lib/api/client';
  import { displayDate, displayValue } from '$lib/utils/format';
  import type { NodeSummary } from '$lib/types/api';

  let nodes = $state<NodeSummary[]>([]);
  let selectedNode = $state<NodeSummary | null>(null);
  let loadingNodes = $state(true);
  let searchQuery = $state('');
  let statusFilter = $state('all');
  let recentIntervalMinutes = $state(60);
  let telemetry = $state<any[]>([]);
  let events = $state<any[]>([]);
  let range = $state('24h');
  let detailState = $state<'idle' | 'loading' | 'error'>('idle');
  let error = $state('');
  let favoriteBusy = $state<string | null>(null);
  let adminCapabilities = $state<any | null>(null);
  let adminCommand = $state('ver');
  let adminConfirmDestructive = $state(false);
  let adminState = $state<'idle' | 'loading' | 'sent' | 'error'>('idle');
  let adminMessage = $state('');
  let adminCredential = $state<{ has_admin_password: boolean; updated_at: string | null } | null>(null);
  let adminPasswordInput = $state('');
  let adminCredentialState = $state<'idle' | 'saving' | 'saved' | 'error'>('idle');
  let adminCredentialMessage = $state('');
  let telemetryRefreshState = $state<'idle' | 'loading' | 'updated' | 'error'>('idle');
  let telemetryRefreshMessage = $state('');
  const hasBatteryPercentageTelemetry = $derived(hasTelemetryMetric('battery_percentage'));
  const hasAltitudeTelemetry = $derived(hasTelemetryMetric('altitude'));
  const hasRssiTelemetry = $derived(hasTelemetryMetric('rssi'));
  const hasSnrTelemetry = $derived(hasTelemetryMetric('snr'));
  const hasNoiseFloorTelemetry = $derived(hasTelemetryMetric('noise_floor'));
  const hasUptimeTelemetry = $derived(hasTelemetryMetric('uptime_seconds'));
  const hasPacketTelemetry = $derived(hasTelemetryMetric('packets_received') || hasTelemetryMetric('packets_sent'));
  const hasErrorTelemetry = $derived(hasTelemetryMetric('packet_receive_errors'));
  const hasHopsTelemetry = $derived(hasTelemetryMetric('hops'));
  const ranges = [
    { label: '1 hour', value: '1h' },
    { label: '12 hours', value: '12h' },
    { label: '1 day', value: '24h' },
    { label: '7 days', value: '7d' },
    { label: '30 days', value: '30d' }
  ];
  const statusFilters = [
    { label: 'All', value: 'all' },
    { label: 'Recent', value: 'recent' },
    { label: 'Stale', value: 'stale' },
    { label: 'Warnings', value: 'warnings' },
    { label: 'Favorites', value: 'favorites' }
  ];
  const recentIntervalOptions = [
    { label: '15 minutes', value: 15 },
    { label: '30 minutes', value: 30 },
    { label: '1 hour', value: 60 },
    { label: '3 hours', value: 180 },
    { label: '6 hours', value: 360 },
    { label: '12 hours', value: 720 },
    { label: '24 hours', value: 1440 }
  ];
  const filteredNodes = $derived(nodes.filter(nodeMatchesFilters));
  const favoriteCount = $derived(nodes.filter((node) => node.is_favorite).length);
  const warningCount = $derived(nodes.filter((node) => node.warning || node.suspect_stale_contact).length);
  const recentCount = $derived(nodes.filter((node) => isRecentNode(node)).length);

  onMount(() => {
    const storedInterval = Number(localStorage.getItem('packetdeck:nodes:recentIntervalMinutes'));
    if (Number.isFinite(storedInterval) && storedInterval > 0) recentIntervalMinutes = storedInterval;
    loadNodes();
  });

  async function loadNodes() {
    loadingNodes = true;
    try {
      error = '';
      nodes = (await apiGet<NodeSummary[]>('/nodes')).sort(sortNodes);
    } catch (err) {
      error = err instanceof Error ? err.message : 'Nodes could not be loaded.';
    } finally {
      loadingNodes = false;
    }
  }

  function routeInfo(node: NodeSummary) {
    const route = node.raw_info?.route;
    return route && typeof route === 'object' ? route : null;
  }

  function hopValue(node: NodeSummary) {
    const route = routeInfo(node);
    return route?.hops ?? 'Unavailable';
  }

  function routeDisplay(node: NodeSummary) {
    const route = routeInfo(node);
    return route?.path_display || route?.path || 'Unavailable';
  }

  function nodeName(node: NodeSummary) {
    return node.display_name ?? node.short_name ?? node.meshcore_id;
  }


  function isRecentNode(node: NodeSummary) {
    if (!node.last_heard_at) return false;
    const ageMs = Date.now() - new Date(node.last_heard_at).getTime();
    return Number.isFinite(ageMs) && ageMs < recentIntervalMinutes * 60 * 1000;
  }

  function nodeMatchesFilters(node: NodeSummary) {
    const query = searchQuery.trim().toLowerCase();
    const matchesQuery = !query || nodeSearchText(node).includes(query);
    if (!matchesQuery) return false;
    if (statusFilter === 'favorites') return Boolean(node.is_favorite);
    if (statusFilter === 'warnings') return Boolean(node.warning || node.suspect_stale_contact);
    if (statusFilter === 'recent') return isRecentNode(node);
    if (statusFilter === 'stale') return Boolean(node.suspect_stale_contact || !isRecentNode(node));
    return true;
  }

  function nodeSearchText(node: NodeSummary) {
    return [
      node.display_name,
      node.short_name,
      node.long_name,
      node.meshcore_id,
      node.public_key,
      node.role,
      node.status,
      routeDisplay(node)
    ]
      .filter(Boolean)
      .join(' ')
      .toLowerCase();
  }

  function lastHeardTone(node: NodeSummary) {
    if (!node.last_heard_at) return 'muted';
    return isRecentNode(node) ? 'fresh' : 'stale';
  }

  function setRecentInterval(value: string | number) {
    const nextValue = Number(value);
    if (!Number.isFinite(nextValue) || nextValue <= 0) return;
    recentIntervalMinutes = nextValue;
    localStorage.setItem('packetdeck:nodes:recentIntervalMinutes', String(nextValue));
  }
  function isRepeaterNode(node: NodeSummary | null) {
    return (node?.role ?? "").toLowerCase().includes("repeater");
  }

  function canMessageNode(node: NodeSummary | null) {
    return !isRepeaterNode(node);
  }


  function hasMetricValue(value: unknown) {
    return value !== null && value !== undefined && value !== '';
  }

  function hasTelemetryMetric(metric: string) {
    return telemetry.some((item) => hasMetricValue(item?.[metric]));
  }

  function latestTelemetryValue(metric: string) {
    return [...telemetry].reverse().find((item) => hasMetricValue(item?.[metric]))?.[metric] ?? null;
  }

  function formatDuration(seconds: unknown) {
    const value = Number(seconds);
    if (!Number.isFinite(value)) return 'Unavailable';
    const days = Math.floor(value / 86400);
    const hours = Math.floor((value % 86400) / 3600);
    const minutes = Math.floor((value % 3600) / 60);
    if (days > 0) return `${days}d ${hours}h`;
    if (hours > 0) return `${hours}h ${minutes}m`;
    return `${minutes}m`;
  }

  function nodeBatteryDisplay(node: NodeSummary) {
    if (hasMetricValue(node.battery_voltage_v)) return displayValue(node.battery_voltage_v, 'V');
    if (hasMetricValue(node.battery_percentage)) return displayValue(node.battery_percentage, '%');
    return 'Unavailable';
  }

  async function openStats(node: NodeSummary) {
    selectedNode = node;
    adminCapabilities = null;
    adminCommand = 'ver';
    adminConfirmDestructive = false;
    adminState = 'idle';
    adminMessage = '';
    adminCredential = null;
    adminPasswordInput = '';
    adminCredentialState = 'idle';
    adminCredentialMessage = '';
    telemetryRefreshState = 'idle';
    telemetryRefreshMessage = '';
    await loadNodeStats();
    await Promise.all([loadAdminCapabilities(), loadAdminCredential()]);
  }

  async function loadNodeStats() {
    if (!selectedNode) return;
    detailState = 'loading';
    try {
      const [history, nodeEvents] = await Promise.all([
        apiGet<any[]>(`/telemetry/nodes/${selectedNode.id}/history?range=${range}&limit=1000`),
        apiGet<any[]>(`/nodes/${selectedNode.id}/events`).catch(() => [])
      ]);
      telemetry = history;
      events = nodeEvents;
      detailState = 'idle';
    } catch (err) {
      detailState = 'error';
      error = err instanceof Error ? err.message : 'Node statistics could not be loaded.';
    }
  }

  function closeStats() {
    selectedNode = null;
    telemetry = [];
    events = [];
    detailState = 'idle';
    adminCapabilities = null;
    adminState = 'idle';
    adminMessage = '';
    adminCredential = null;
    adminPasswordInput = '';
    adminCredentialState = 'idle';
    adminCredentialMessage = '';
    telemetryRefreshState = 'idle';
    telemetryRefreshMessage = '';
  }

  async function changeRange(nextRange: string) {
    range = nextRange;
    await loadNodeStats();
  }

  async function toggleFavorite(node: NodeSummary, event?: MouseEvent) {
    event?.stopPropagation();
    favoriteBusy = node.id;
    try {
      const updated = await apiPatch<NodeSummary>(`/nodes/${node.id}/favorite`, {
        is_favorite: !node.is_favorite
      });
      nodes = nodes
        .map((item) => (item.id === updated.id ? updated : item))
        .sort(sortNodes);
      if (selectedNode?.id === updated.id) selectedNode = updated;
    } catch (err) {
      error = err instanceof Error ? err.message : 'Favorite state could not be saved.';
    } finally {
      favoriteBusy = null;
    }
  }

  function sortNodes(a: NodeSummary, b: NodeSummary) {
    if (Boolean(a.is_favorite) !== Boolean(b.is_favorite)) return a.is_favorite ? -1 : 1;
    return new Date(b.last_heard_at ?? 0).getTime() - new Date(a.last_heard_at ?? 0).getTime();
  }

  async function loadAdminCapabilities() {
    if (!selectedNode) return;
    try {
      adminCapabilities = await apiGet<any>(`/nodes/${selectedNode.id}/admin/capabilities`);
    } catch (err) {
      adminCapabilities = {
        supported: false,
        reason: err instanceof Error ? err.message : 'Remote administration capabilities could not be loaded.'
      };
    }
  }

  async function loadAdminCredential() {
    if (!selectedNode) return;
    try {
      adminCredential = await apiGet<{ has_admin_password: boolean; updated_at: string | null }>(
        `/nodes/${selectedNode.id}/admin/credential`
      );
    } catch (err) {
      adminCredential = { has_admin_password: false, updated_at: null };
      adminCredentialMessage = err instanceof Error ? err.message : 'Admin password state could not be loaded.';
    }
  }

  async function saveAdminCredential() {
    if (!selectedNode || !adminPasswordInput.trim()) return;
    adminCredentialState = 'saving';
    adminCredentialMessage = '';
    try {
      adminCredential = await apiPut<{ has_admin_password: boolean; updated_at: string | null }>(
        `/nodes/${selectedNode.id}/admin/credential`,
        { admin_password: adminPasswordInput }
      );
      adminPasswordInput = '';
      adminCredentialState = 'saved';
      adminCredentialMessage = 'Admin password saved.';
    } catch (err) {
      adminCredentialState = 'error';
      adminCredentialMessage = err instanceof Error ? err.message : 'Admin password could not be saved.';
    }
  }

  async function deleteAdminCredential() {
    if (!selectedNode) return;
    adminCredentialState = 'saving';
    adminCredentialMessage = '';
    try {
      await apiDelete(`/nodes/${selectedNode.id}/admin/credential`);
      adminCredential = { has_admin_password: false, updated_at: null };
      adminPasswordInput = '';
      adminCredentialState = 'saved';
      adminCredentialMessage = 'Admin password removed.';
    } catch (err) {
      adminCredentialState = 'error';
      adminCredentialMessage = err instanceof Error ? err.message : 'Admin password could not be removed.';
    }
  }

  function selectAdminPreset(command: string) {
    adminCommand = command;
    adminConfirmDestructive = false;
    adminState = 'idle';
    adminMessage = '';
  }

  function isDestructiveAdminCommand(command = adminCommand) {
    const normalized = command.trim().toLowerCase();
    return ['reboot', 'clkreboot', 'start ota', 'erase', 'factory-reset'].some(
      (prefix) => normalized === prefix || normalized.startsWith(`${prefix} `)
    ) || normalized.startsWith('password ') || normalized.startsWith('set prv.key');
  }

  async function refreshNodeTelemetry(node: NodeSummary, event?: MouseEvent) {
    event?.stopPropagation();
    telemetryRefreshState = 'loading';
    telemetryRefreshMessage = '';
    try {
      const result = await apiPost<any>(`/nodes/${node.id}/telemetry/refresh`, {});
      telemetryRefreshState = 'updated';
      telemetryRefreshMessage = 'Telemetry refreshed.';
      await Promise.all([loadNodes(), loadNodeStats()]);
      if (selectedNode?.id === node.id) {
        selectedNode = nodes.find((item) => item.id === node.id) ?? selectedNode;
      }
    } catch (err) {
      telemetryRefreshState = 'error';
      telemetryRefreshMessage = err instanceof Error ? err.message : 'Telemetry refresh failed.';
    }
  }

  async function removeNodeContact(node: NodeSummary, event?: MouseEvent) {
    event?.stopPropagation();
    if (!confirm(`Remove contact ${nodeName(node)} from PacketDeck and the MeshCore device?`)) return;
    try {
      await apiDelete(`/nodes/${node.id}/contact`);
      if (selectedNode?.id === node.id) closeStats();
      await loadNodes();
    } catch (err) {
      error = err instanceof Error ? err.message : 'Contact could not be removed.';
    }
  }

  async function sendAdminCommand() {
    if (!selectedNode) return;
    adminState = 'loading';
    adminMessage = '';
    try {
      const result = await apiPost<any>(`/nodes/${selectedNode.id}/admin/commands`, {
        command: adminCommand,
        confirm_destructive: adminConfirmDestructive
      });
      adminState = 'sent';
      adminMessage = result.command_response?.body
        ? String(result.command_response.body)
        : 'Command sent. Waiting for the remote node reply in Messages.';
      adminConfirmDestructive = false;
    } catch (err) {
      adminState = 'error';
      adminMessage = err instanceof Error ? err.message : 'Remote command could not be sent.';
    }
  }
</script>


<section class="page">
  <div class="page-header">
    <div>
      <h1>Nodes</h1>
      <p class="muted">Known MeshCore clients, status, location, signal metrics, and metadata.</p>
    </div>
    <button class="secondary" onclick={loadNodes}>Refresh</button>
  </div>

  <section class="node-toolbar">
    <label class="search-field">
      <span>Search nodes</span>
      <input bind:value={searchQuery} placeholder="Name, key, role, route" />
    </label>
    <label class="recent-setting">
      <span>Recent window</span>
      <select value={recentIntervalMinutes} onchange={(event) => setRecentInterval(event.currentTarget.value)}>
        {#each recentIntervalOptions as option}
          <option value={option.value}>{option.label}</option>
        {/each}
      </select>
    </label>
    <div class="filter-tabs" aria-label="Node filters">
      {#each statusFilters as filter}
        <button
          class:active={statusFilter === filter.value}
          class="secondary"
          type="button"
          onclick={() => (statusFilter = filter.value)}
        >
          {filter.label}
        </button>
      {/each}
    </div>
  </section>

  <section class="node-overview" aria-label="Node overview">
    <article>
      <span>Total</span>
      <strong>{nodes.length}</strong>
    </article>
    <article>
      <span>Recent</span>
      <strong>{recentCount}</strong>
    </article>
    <article>
      <span>Favorites</span>
      <strong>{favoriteCount}</strong>
    </article>
    <article class:attention={warningCount > 0}>
      <span>Warnings</span>
      <strong>{warningCount}</strong>
    </article>
  </section>

  {#if error}
    <div class="card">{error}</div>
  {:else if loadingNodes}
    <div class="card">Loading nodes...</div>
  {:else if nodes.length === 0}
    <div class="card">No nodes have been discovered yet.</div>
  {:else if filteredNodes.length === 0}
    <div class="card">No nodes match the current filters.</div>
  {:else}
    <div class="nodes-table-wrap">
      <table class="nodes-table">
        <thead>
          <tr>
            <th>Node</th>
            <th>Status</th>
            <th>Signal</th>
            <th>Route</th>
            <th>Last heard</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {#each filteredNodes as node}
            <tr class:favorite-row={node.is_favorite} onclick={() => openStats(node)}>
              <td>
                <div class="node-identity">
                  <button
                    class="favorite-toggle"
                    class:active={node.is_favorite}
                    disabled={favoriteBusy === node.id}
                    title={node.is_favorite ? 'Remove favorite' : 'Mark as favorite'}
                    aria-label={node.is_favorite ? 'Remove favorite' : 'Mark as favorite'}
                    onclick={(event) => toggleFavorite(node, event)}
                  >
                    {node.is_favorite ? '★' : '☆'}
                  </button>
                  <div>
                    <strong>{node.display_name ?? node.short_name ?? 'Unnamed node'}</strong>
                    <span>{node.role ?? 'Unknown'} · {node.meshcore_id}</span>
                  </div>
                </div>
              </td>
              <td>
                <div class="status-stack">
                  <StatusPill status={node.status} />
                  {#if node.warning}
                    <span class="warning-pill" title={node.warning}>Duplicate</span>
                  {:else if node.suspect_stale_contact}
                    <span class="warning-pill">Stale contact</span>
                  {/if}
                </div>
              </td>
              <td>
                <div class="metric-stack">
                  <span>{nodeBatteryDisplay(node)}</span>
                  <small>{displayValue(node.rssi, 'dBm')} · {displayValue(node.snr, 'dB')}</small>
                </div>
              </td>
              <td>
                <div class="route-stack">
                  <span>{hopValue(node)} hops</span>
                  <small title={routeDisplay(node)}>{routeDisplay(node)}</small>
                </div>
              </td>
              <td><span class:last-fresh={lastHeardTone(node) === 'fresh'} class:last-stale={lastHeardTone(node) === 'stale'}>{displayDate(node.last_heard_at)}</span></td>
              <td>
                <div class="node-actions">
                  {#if canMessageNode(node)}
                  <a
                    class="message-button"
                    href={`/messages?node=${node.id}`}
                    onclick={(event) => event.stopPropagation()}
                  >
                    Message
                  </a>
                  {/if}
                  {#if node.warning || node.suspect_stale_contact}
                    <button class="secondary compact-danger" onclick={(event) => removeNodeContact(node, event)}>
                      Remove
                    </button>
                  {/if}
                </div>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>

    <div class="node-card-grid">
      {#each filteredNodes as node}
        <article class={`node-card ${node.is_favorite ? "favorite-card" : ""}`} onclick={() => openStats(node)}>
          <header>
            <button
              class="favorite-toggle"
              class:active={node.is_favorite}
              disabled={favoriteBusy === node.id}
              title={node.is_favorite ? 'Remove favorite' : 'Mark as favorite'}
              aria-label={node.is_favorite ? 'Remove favorite' : 'Mark as favorite'}
              onclick={(event) => toggleFavorite(node, event)}
            >
              {node.is_favorite ? '★' : '☆'}
            </button>
            <div>
              <h2>{node.display_name ?? node.short_name ?? 'Unnamed node'}</h2>
              <p>{node.role ?? 'Unknown'} · {node.meshcore_id}</p>
            </div>
            <StatusPill status={node.status} />
          </header>

          {#if node.warning || node.suspect_stale_contact}
            <div class="card-warning">
              {node.warning ?? 'This contact looks stale or incomplete.'}
            </div>
          {/if}

          <div class="card-metrics">
            <div><span>Battery</span><strong>{nodeBatteryDisplay(node)}</strong></div>
            <div><span>Signal</span><strong>{displayValue(node.rssi, 'dBm')} / {displayValue(node.snr, 'dB')}</strong></div>
            <div><span>Hops</span><strong>{hopValue(node)}</strong></div>
            <div><span>Last heard</span><strong class:last-fresh={lastHeardTone(node) === 'fresh'} class:last-stale={lastHeardTone(node) === 'stale'}>{displayDate(node.last_heard_at)}</strong></div>
          </div>

          <div class="card-route" title={routeDisplay(node)}>{routeDisplay(node)}</div>

          <footer>
            {#if canMessageNode(node)}
            <a
              class="message-button"
              href={`/messages?node=${node.id}`}
              onclick={(event) => event.stopPropagation()}
            >
              Message
            </a>
            {/if}
            {#if node.warning || node.suspect_stale_contact}
              <button class="secondary compact-danger" onclick={(event) => removeNodeContact(node, event)}>
                Remove
              </button>
            {/if}
          </footer>
        </article>
      {/each}
    </div>
  {/if}

  {#if selectedNode}
    <div
      class="modal-backdrop"
      role="presentation"
      tabindex="-1"
      onclick={(event) => {
        if (event.target === event.currentTarget) closeStats();
      }}
      onkeydown={(event) => {
        if (event.key === 'Escape') closeStats();
      }}
    >
      <div class="modal" role="dialog" aria-modal="true" aria-label="Node statistics">
        <header class="modal-header">
          <div>
            <h2>{selectedNode.display_name ?? selectedNode.short_name ?? selectedNode.meshcore_id}</h2>
            <p class="muted">{selectedNode.role ?? 'Unknown'}</p>
          </div>
          <div class="modal-actions">
            {#if canMessageNode(selectedNode)}
            <a class="secondary message-button" href={`/messages?node=${selectedNode.id}`}>Message</a>
            {/if}
            <button class="secondary" disabled={telemetryRefreshState === 'loading'} onclick={(event) => refreshNodeTelemetry(selectedNode!, event)}>
              {telemetryRefreshState === 'loading' ? 'Refreshing...' : 'Refresh telemetry'}
            </button>
            <button
              class="secondary"
              disabled={favoriteBusy === selectedNode.id}
              onclick={(event) => selectedNode && toggleFavorite(selectedNode, event)}
            >
              {selectedNode.is_favorite ? 'Remove favorite' : 'Mark favorite'}
            </button>
            <button class="secondary" onclick={closeStats}>Close</button>
          </div>
        </header>

        <div class="summary-grid">
          <div><span>Status</span><strong>{selectedNode.status}</strong></div>
          <div><span>Last heard</span><strong>{displayDate(selectedNode.last_heard_at)}</strong></div>
          <div><span>Battery voltage</span><strong>{nodeBatteryDisplay(selectedNode)}</strong></div>
          <div><span>RSSI</span><strong>{displayValue(latestTelemetryValue('rssi'), 'dBm')}</strong></div>
          <div><span>SNR</span><strong>{displayValue(latestTelemetryValue('snr'), 'dB')}</strong></div>
          <div><span>Uptime</span><strong>{formatDuration(latestTelemetryValue('uptime_seconds'))}</strong></div>
          <div><span>RX / TX</span><strong>{displayValue(latestTelemetryValue('packets_received'))} / {displayValue(latestTelemetryValue('packets_sent'))}</strong></div>
          <div><span>Hops</span><strong>{hopValue(selectedNode)}</strong></div>
          <div class="wide"><span>Route</span><strong>{routeDisplay(selectedNode)}</strong></div>
          <div class="wide"><span>Public key</span><strong>{selectedNode.public_key ?? 'Unavailable'}</strong></div>
        </div>

        {#if telemetryRefreshMessage}
          <div class:warning-panel={telemetryRefreshState !== 'error'} class:error-panel={telemetryRefreshState === 'error'}>
            <strong>{telemetryRefreshMessage}</strong>
          </div>
        {/if}

        {#if selectedNode.warning || selectedNode.suspect_stale_contact}
          <div class="warning-panel">
            <strong>{selectedNode.warning ?? 'This contact looks stale or incomplete.'}</strong>
            {#if selectedNode.duplicate_nodes?.length}
              <span>Conflicts: {selectedNode.duplicate_nodes.map((item) => item.display_name ?? item.public_key ?? item.meshcore_id).join(', ')}</span>
            {/if}
            <button class="secondary compact-danger" onclick={(event) => removeNodeContact(selectedNode!, event)}>Remove contact</button>
          </div>
        {/if}

        <section class="remote-admin">
          <header>
            <div>
              <h3>Remote Administration</h3>
              <p class="muted">
                Sends MeshCore CLI commands to router, repeater, or room server nodes. Replies arrive as normal messages.
              </p>
            </div>
          </header>

          {#if !adminCapabilities}
            <div class="card">Loading remote administration capabilities...</div>
          {:else if !adminCapabilities.supported}
            <div class="card">{adminCapabilities.reason}</div>
          {:else}
            <div class="credential-panel">
              <div>
                <strong>Admin password</strong>
                <span>
                  {adminCredential?.has_admin_password
                    ? `Saved${adminCredential.updated_at ? ` · ${displayDate(adminCredential.updated_at)}` : ''}`
                    : 'Not saved'}
                </span>
              </div>
              <div class="credential-form">
                <input
                  type="password"
                  bind:value={adminPasswordInput}
                  placeholder={adminCredential?.has_admin_password ? 'Replace saved password' : 'Admin password'}
                  autocomplete="new-password"
                  maxlength="128"
                />
                <button
                  class="secondary"
                  disabled={adminCredentialState === 'saving' || !adminPasswordInput.trim()}
                  onclick={saveAdminCredential}
                >
                  {adminCredentialState === 'saving' ? 'Saving...' : 'Save'}
                </button>
                {#if adminCredential?.has_admin_password}
                  <button
                    class="secondary"
                    disabled={adminCredentialState === 'saving'}
                    onclick={deleteAdminCredential}
                  >
                    Remove
                  </button>
                {/if}
              </div>
              {#if adminCredentialMessage}
                <p class:error-text={adminCredentialState === 'error'}>{adminCredentialMessage}</p>
              {/if}
            </div>

            <div class="preset-grid">
              {#each adminCapabilities.presets as preset}
                <button
                  class="secondary"
                  class:danger={preset.destructive}
                  onclick={() => selectAdminPreset(preset.command)}
                >
                  {preset.label}
                </button>
              {/each}
            </div>

            <label class="command-field">
              <span>Command</span>
              <input bind:value={adminCommand} placeholder="ver" maxlength="180" />
            </label>

            {#if isDestructiveAdminCommand()}
              <label class="confirm-row">
                <input type="checkbox" bind:checked={adminConfirmDestructive} />
                <span>Confirm command that may change, reboot, or reset the remote node.</span>
              </label>
            {/if}

            <div class="admin-actions">
              <button
                disabled={adminState === 'loading' || !adminCommand.trim() || (isDestructiveAdminCommand() && !adminConfirmDestructive)}
                onclick={sendAdminCommand}
              >
                {adminState === 'loading' ? 'Sending...' : 'Send command'}
              </button>
              <span class:error-text={adminState === 'error'}>{adminMessage}</span>
            </div>
          {/if}
        </section>

        <div class="range-tabs">
          {#each ranges as item}
            <button class:active={range === item.value} onclick={() => changeRange(item.value)}>{item.label}</button>
          {/each}
        </div>

        {#if detailState === 'loading'}
          <div class="card">Loading node statistics...</div>
        {:else}
          <div class="chart-grid">
            <MetricChart title="Battery voltage" metric="battery_voltage_v" unit="V" data={telemetry} />
            {#if hasBatteryPercentageTelemetry}
              <MetricChart title="Battery percentage" metric="battery_percentage" unit="%" data={telemetry} />
            {/if}
            {#if hasUptimeTelemetry}
              <MetricChart title="Uptime" metric="uptime_seconds" unit="s" data={telemetry} />
            {/if}
            {#if hasPacketTelemetry}
              <MetricChart title="Packets received" metric="packets_received" data={telemetry} />
              <MetricChart title="Packets sent" metric="packets_sent" data={telemetry} />
            {/if}
            {#if hasErrorTelemetry}
              <MetricChart title="Receive errors" metric="packet_receive_errors" data={telemetry} />
            {/if}
            {#if hasHopsTelemetry}
              <MetricChart title="Hops" metric="hops" data={telemetry} />
            {/if}
            {#if hasRssiTelemetry}
              <MetricChart title="RSSI" metric="rssi" unit="dBm" data={telemetry} />
            {/if}
            {#if hasSnrTelemetry}
              <MetricChart title="SNR" metric="snr" unit="dB" data={telemetry} />
            {/if}
            {#if hasNoiseFloorTelemetry}
              <MetricChart title="Noise floor" metric="noise_floor" unit="dBm" data={telemetry} />
            {/if}
            {#if hasAltitudeTelemetry}
              <MetricChart title="Altitude" metric="altitude" unit="m" data={telemetry} />
            {/if}
          </div>

          <section class="events">
            <h3>Events</h3>
            {#if events.length === 0}
              <p class="muted">No events are available for this node.</p>
            {:else}
              <div class="event-list">
                {#each events.slice(0, 20) as event}
                  <article>
                    <strong>{event.event_type}</strong>
                    <span>{displayDate(event.created_at)}</span>
                  </article>
                {/each}
              </div>
            {/if}
          </section>
        {/if}
      </div>
    </div>
  {/if}
</section>

<style>
  h2 {
    margin: 0 0 0.5rem;
    font-size: 1.1rem;
  }

  .node-toolbar {
    display: grid;
    grid-template-columns: minmax(16rem, 26rem) minmax(10rem, 12rem) 1fr;
    gap: 0.85rem;
    align-items: end;
  }

  .search-field,
  .recent-setting {
    display: grid;
    gap: 0.35rem;
  }

  .search-field span,
  .recent-setting span {
    color: var(--muted);
    font-size: 0.78rem;
    font-weight: 800;
    text-transform: uppercase;
  }

  .search-field input,
  .recent-setting select {
    width: 100%;
    min-width: 0;
    box-sizing: border-box;
  }

  .filter-tabs {
    display: flex;
    flex-wrap: wrap;
    gap: 0.45rem;
    justify-content: end;
  }

  .filter-tabs button {
    min-height: 2.35rem;
    padding: 0.4rem 0.7rem;
  }

  .filter-tabs button.active {
    border-color: rgba(45, 212, 191, 0.55);
    background: var(--accent-soft);
    color: var(--text-strong);
  }

  .node-overview {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 0.75rem;
  }

  .node-overview article {
    display: grid;
    gap: 0.2rem;
    min-width: 0;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: linear-gradient(180deg, rgba(16, 24, 39, 0.94), rgba(12, 20, 34, 0.94));
    padding: 0.8rem;
  }

  .node-overview article.attention {
    border-color: rgba(245, 158, 11, 0.4);
    background: rgba(245, 158, 11, 0.1);
  }

  .node-overview span {
    color: var(--muted);
    font-size: 0.78rem;
    font-weight: 800;
  }

  .node-overview strong {
    color: var(--text-strong);
    font-size: 1.45rem;
  }

  .nodes-table-wrap {
    overflow: auto;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: var(--surface);
  }

  .nodes-table {
    min-width: 920px;
    border-radius: 0;
  }

  .nodes-table th {
    position: sticky;
    top: 0;
    z-index: 1;
    background: var(--surface);
  }

  .nodes-table tr {
    cursor: pointer;
  }

  .nodes-table tbody tr:hover {
    background: rgba(45, 212, 191, 0.06);
  }

  .nodes-table tbody tr.favorite-row {
    background: rgba(245, 158, 11, 0.045);
  }

  .node-identity {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr);
    gap: 0.7rem;
    align-items: center;
    min-width: 16rem;
  }

  .node-identity strong,
  .node-card h2 {
    display: block;
    min-width: 0;
    overflow: hidden;
    color: var(--text-strong);
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .node-identity span,
  .metric-stack small,
  .route-stack small,
  .node-card p,
  .card-route {
    color: var(--muted);
    font-size: 0.8rem;
  }

  .node-identity span,
  .route-stack small,
  .card-route {
    display: block;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .favorite-toggle {
    display: grid;
    width: 2.25rem;
    min-width: 2.25rem;
    height: 2.25rem;
    min-height: 2.25rem;
    place-items: center;
    border-color: rgba(148, 163, 184, 0.26);
    background: rgba(15, 23, 42, 0.74);
    padding: 0;
    color: var(--muted);
    font-size: 1rem;
    box-shadow: none;
  }

  .favorite-toggle.active {
    border-color: rgba(245, 158, 11, 0.6);
    background: rgba(245, 158, 11, 0.16);
    color: #fbbf24;
  }

  .status-stack,
  .metric-stack,
  .route-stack {
    display: grid;
    gap: 0.28rem;
    min-width: 0;
  }

  .metric-stack span,
  .route-stack span {
    color: var(--text-strong);
    font-weight: 800;
  }

  .last-fresh {
    color: #99f6e4;
    font-weight: 800;
  }

  .last-stale {
    color: #fde68a;
    font-weight: 800;
  }

  .node-card-grid {
    display: none;
    grid-template-columns: repeat(auto-fit, minmax(18rem, 1fr));
    gap: 0.85rem;
  }

  .node-card {
    display: grid;
    gap: 0.8rem;
    min-width: 0;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: linear-gradient(180deg, rgba(16, 24, 39, 0.96), rgba(12, 20, 34, 0.96));
    padding: 0.85rem;
    cursor: pointer;
  }

  .node-card.favorite-card {
    border-color: rgba(245, 158, 11, 0.26);
  }

  .node-card header {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr) auto;
    gap: 0.65rem;
    align-items: start;
  }

  .node-card h2,
  .node-card p {
    margin: 0;
  }

  .card-warning {
    border: 1px solid rgba(245, 158, 11, 0.34);
    border-radius: 8px;
    background: rgba(245, 158, 11, 0.1);
    padding: 0.55rem 0.65rem;
    color: #fde68a;
    font-size: 0.82rem;
    font-weight: 750;
    overflow-wrap: anywhere;
  }

  .card-metrics {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 0.55rem;
  }

  .card-metrics div {
    display: grid;
    gap: 0.15rem;
    min-width: 0;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: rgba(15, 23, 42, 0.38);
    padding: 0.58rem;
  }

  .card-metrics span {
    color: var(--muted);
    font-size: 0.72rem;
    font-weight: 800;
    text-transform: uppercase;
  }

  .card-metrics strong {
    min-width: 0;
    overflow-wrap: anywhere;
    color: var(--text-strong);
    font-size: 0.88rem;
  }

  .card-route {
    border-top: 1px solid var(--border);
    padding-top: 0.65rem;
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  }

  .node-card footer {
    display: flex;
    flex-wrap: wrap;
    gap: 0.45rem;
  }

  tr {
    cursor: pointer;
  }


  .message-button {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-height: 2rem;
    border: 1px solid rgba(20, 184, 166, 0.34);
    border-radius: 8px;
    background: rgba(20, 184, 166, 0.12);
    padding: 0.25rem 0.55rem;
    color: var(--text-strong);
    font-size: 0.74rem;
    font-weight: 850;
    text-decoration: none;
    white-space: nowrap;
  }

  .node-actions {
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem;
    align-items: center;
  }

  .warning-pill {
    display: inline-flex;
    align-items: center;
    min-height: 1.6rem;
    border: 1px solid rgba(245, 158, 11, 0.38);
    border-radius: 999px;
    background: rgba(245, 158, 11, 0.12);
    padding: 0.15rem 0.5rem;
    color: #fde68a;
    font-size: 0.72rem;
    font-weight: 850;
  }

  .compact-danger {
    min-height: 2rem;
    border-color: rgba(248, 113, 113, 0.42);
    background: rgba(248, 113, 113, 0.12);
    padding: 0.25rem 0.55rem;
    color: #fecaca;
    font-size: 0.74rem;
  }

  .warning-panel {
    display: grid;
    gap: 0.5rem;
    border: 1px solid rgba(245, 158, 11, 0.38);
    border-radius: 8px;
    background: rgba(245, 158, 11, 0.1);
    padding: 0.8rem;
    color: #fde68a;
  }

  .warning-panel span {
    color: var(--muted);
    overflow-wrap: anywhere;
  }

  .error-panel {
    display: grid;
    gap: 0.5rem;
    border: 1px solid rgba(248, 113, 113, 0.42);
    border-radius: 8px;
    background: rgba(248, 113, 113, 0.12);
    padding: 0.8rem;
    color: #fecaca;
  }

  .message-button:hover,
  .message-button:focus-visible {
    border-color: rgba(20, 184, 166, 0.6);
    background: rgba(20, 184, 166, 0.2);
  }

  .modal-backdrop {
    position: fixed;
    inset: 0;
    z-index: 50;
    display: grid;
    place-items: center;
    background: rgba(2, 6, 23, 0.72);
    padding: 1rem;
  }

  .modal {
    display: grid;
    gap: 1rem;
    width: min(1080px, 100%);
    max-height: min(900px, calc(100vh - 2rem));
    overflow: auto;
    border: 1px solid var(--border);
    border-radius: 12px;
    background: var(--surface);
    padding: 1rem;
    box-shadow: 0 24px 80px rgba(0, 0, 0, 0.35);
  }

  .modal-header {
    display: flex;
    align-items: start;
    justify-content: space-between;
    gap: 1rem;
    border-bottom: 1px solid var(--border);
    padding-bottom: 0.8rem;
  }

  .modal-header h2 {
    margin: 0;
    font-size: 1.35rem;
  }

  .modal-actions,
  .admin-actions {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: end;
    gap: 0.5rem;
  }

  .summary-grid {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 0.7rem;
  }

  .summary-grid div {
    display: grid;
    gap: 0.2rem;
    min-width: 0;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: var(--surface-soft);
    padding: 0.75rem;
  }

  .summary-grid .wide {
    grid-column: span 2;
  }

  .summary-grid span,
  .events article span {
    color: var(--muted);
    font-size: 0.78rem;
    font-weight: 700;
  }

  .summary-grid strong {
    min-width: 0;
    overflow-wrap: anywhere;
    color: var(--text-strong);
  }

  .range-tabs {
    display: flex;
    flex-wrap: wrap;
    gap: 0.45rem;
  }

  .remote-admin {
    display: grid;
    gap: 0.75rem;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: var(--surface-soft);
    padding: 0.85rem;
  }

  .remote-admin header {
    display: flex;
    justify-content: space-between;
    gap: 1rem;
  }

  .remote-admin h3 {
    margin: 0;
  }

  .remote-admin p {
    margin: 0.25rem 0 0;
  }

  .preset-grid {
    display: flex;
    flex-wrap: wrap;
    gap: 0.45rem;
  }

  .credential-panel {
    display: grid;
    gap: 0.55rem;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: rgba(15, 23, 42, 0.34);
    padding: 0.75rem;
  }

  .credential-panel > div:first-child {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    justify-content: space-between;
    gap: 0.5rem;
  }

  .credential-panel strong {
    color: var(--text-strong);
  }

  .credential-panel span,
  .credential-panel p {
    margin: 0;
    color: var(--muted);
    font-size: 0.82rem;
    font-weight: 750;
  }

  .credential-panel .error-text {
    color: #fecaca;
  }

  .credential-form {
    display: grid;
    grid-template-columns: minmax(10rem, 1fr) auto auto;
    gap: 0.5rem;
  }

  .credential-form input {
    min-width: 0;
  }

  .preset-grid button {
    min-height: 2.15rem;
    padding: 0.35rem 0.65rem;
  }

  .preset-grid button.danger {
    border-color: rgba(248, 113, 113, 0.4);
    color: #fecaca;
  }

  .command-field {
    display: grid;
    gap: 0.35rem;
  }

  .command-field span,
  .confirm-row {
    color: var(--muted);
    font-size: 0.82rem;
    font-weight: 750;
  }

  .command-field input {
    width: 100%;
  }

  .confirm-row {
    display: flex;
    align-items: center;
    gap: 0.45rem;
  }

  .admin-actions {
    justify-content: start;
  }

  .admin-actions span {
    color: var(--muted);
    font-size: 0.84rem;
    font-weight: 750;
  }

  .admin-actions .error-text {
    color: #fecaca;
  }

  .range-tabs button {
    min-height: 2.15rem;
    padding: 0.35rem 0.65rem;
  }

  .range-tabs button.active {
    border-color: rgba(45, 212, 191, 0.46);
    background: var(--accent-soft);
    color: var(--text-strong);
  }

  .chart-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 0.8rem;
  }

  .events {
    display: grid;
    gap: 0.65rem;
  }

  .events h3 {
    margin: 0;
  }

  .event-list {
    display: grid;
    gap: 0.45rem;
  }

  .events article {
    display: flex;
    justify-content: space-between;
    gap: 1rem;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: var(--surface-soft);
    padding: 0.65rem 0.75rem;
  }

  @media (max-width: 980px) {
    .node-toolbar {
      grid-template-columns: 1fr;
      align-items: stretch;
    }

    .filter-tabs {
      justify-content: start;
    }

    .node-overview {
      grid-template-columns: repeat(3, minmax(0, 1fr));
    }

    .nodes-table-wrap {
      display: none;
    }

    .node-card-grid {
      display: grid;
    }
  }

  @media (max-width: 820px) {
    .summary-grid,
    .chart-grid {
      grid-template-columns: 1fr;
    }

    .summary-grid .wide {
      grid-column: auto;
    }

    .credential-form {
      grid-template-columns: 1fr;
    }
  }

  @media (max-width: 560px) {
    .node-overview,
    .card-metrics {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    .page-header {
      align-items: stretch;
      flex-direction: column;
    }

    .filter-tabs button {
      flex: 1 1 7rem;
    }

    .node-card {
      padding: 0.75rem;
    }

    .node-card header {
      grid-template-columns: auto minmax(0, 1fr);
    }

    .node-card header :global(.status-pill) {
      grid-column: 1 / -1;
      width: fit-content;
    }

    .modal-backdrop {
      padding: 0.5rem;
    }
  }
</style>
