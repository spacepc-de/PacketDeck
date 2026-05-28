<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import MetricChart from '$lib/components/MetricChart.svelte';
  import { apiGet, apiPost } from '$lib/api/client';
  import { latestEvent } from '$lib/stores/events';
  import { displayValue } from '$lib/utils/format';
  import type { ApiEvent, ConnectionStatus, GatewayTelemetry } from '$lib/types/api';

  type TileSize = 'small' | 'medium' | 'large' | 'wide';
  type DashboardTile = {
    id: string;
    title: string;
    size: TileSize;
    type: 'device' | 'metric' | 'group' | 'chart' | 'activity';
    metric?: keyof GatewayTelemetry;
    unit?: string;
    charts?: { title: string; metric: keyof GatewayTelemetry; unit?: string }[];
  };

  const layoutKey = 'meshcore-dashboard-layout-v4';
  const rangeKey = 'meshcore-dashboard-time-range';
  const liveLogLimitKey = 'packetdeck-dashboard-live-log-limit';
  const liveLogFiltersKey = 'packetdeck-dashboard-live-log-filters';
  const liveLogTypeFilters = [
    { label: 'Messages', value: 'messages' },
    { label: 'Adverts', value: 'adverts' },
    { label: 'Telemetry', value: 'telemetry' },
    { label: 'Nodes', value: 'nodes' },
    { label: 'Automations', value: 'automations' },
    { label: 'Connection', value: 'connection' },
    { label: 'System', value: 'system' },
    { label: 'Raw MeshCore', value: 'meshcore' }
  ];
  const liveLogSourceFilters = [
    { label: 'MeshCore', value: 'meshcore' },
    { label: 'Application', value: 'app' }
  ];
  const liveLogSeverityFilters = [
    { label: 'Info', value: 'info' },
    { label: 'Warning', value: 'warning' },
    { label: 'Error', value: 'error' }
  ];
  const meshEventTypes = [
    'connection.status_changed',
    'telemetry.gateway_updated',
    'telemetry.node_updated',
    'node.discovered',
    'node.updated',
    'node.status_changed',
    'meshcore.advertisement',
    'meshcore.advert_sent',
    'message.received',
    'message.sent',
    'message.delivery_updated',
    'automation.triggered',
    'automation.completed',
    'system.error'
  ];
  const timeRanges = [
    { label: 'Last hour', value: '1h' },
    { label: 'Last 12 hours', value: '12h' },
    { label: 'Last day', value: '24h' },
    { label: 'Last 7 days', value: '7d' },
    { label: 'Last 30 days', value: '30d' }
  ];
  const sizeOrder: TileSize[] = ['small', 'medium', 'large', 'wide'];
  const defaultTiles: DashboardTile[] = [
    { id: 'device', title: 'Device', size: 'medium', type: 'device' },
    { id: 'radio', title: 'Radio', size: 'medium', type: 'group' },
    { id: 'signal', title: 'Signal', size: 'medium', type: 'group' },
    {
      id: 'power-history',
      title: 'Power history',
      size: 'wide',
      type: 'chart',
      charts: [
        { title: 'Battery voltage', metric: 'battery_voltage_v', unit: 'V' },
        { title: 'Ch1 voltage', metric: 'ch1_voltage_v', unit: 'V' }
      ]
    },
    {
      id: 'network-history',
      title: 'Network history',
      size: 'wide',
      type: 'chart',
      charts: [
        { title: 'Node count', metric: 'node_count' },
        { title: 'RSSI', metric: 'last_rssi', unit: 'dBm' },
        { title: 'SNR', metric: 'last_snr', unit: 'dB' }
      ]
    }
  ];

  let connection = $state<ConnectionStatus | null>(null);
  let telemetry = $state<GatewayTelemetry | null>(null);
  let history = $state<GatewayTelemetry[]>([]);
  let tiles = $state<DashboardTile[]>(defaultTiles);
  let range = $state('24h');
  let error = $state('');
  let loading = $state(true);
  let refreshing = $state(false);
  let draggedTileId = $state<string | null>(null);
  let liveLog = $state<ApiEvent[]>([]);
  let liveLogLimit = $state(50);
  let liveLogError = $state('');
  let liveLogTypes = $state<string[]>(liveLogTypeFilters.map((item) => item.value));
  let liveLogSources = $state<string[]>(liveLogSourceFilters.map((item) => item.value));
  let liveLogSeverities = $state<string[]>(liveLogSeverityFilters.map((item) => item.value));
  let selectedLiveLogEvent = $state<ApiEvent | null>(null);
  let advertSending = $state(false);
  let advertStatus = $state('');
  let advertError = $state('');
  let refreshTimer: ReturnType<typeof setInterval> | undefined;
  let closeLiveEvents: (() => void) | undefined;
  const activeRangeLabel = $derived(timeRanges.find((item) => item.value === range)?.label ?? 'Last day');
  const filteredLiveLog = $derived(liveLog.filter(liveLogMatchesFilters));
  const visibleLiveLog = $derived(filteredLiveLog.slice(-liveLogLimit).reverse());

  onMount(async () => {
    loadLayout();
    loadRange();
    loadLiveLogLimit();
    loadLiveLogFilters();
    await loadDashboard();
    await loadLiveLog();
    closeLiveEvents = latestEvent.subscribe((event) => {
      if (event && isMeshEvent(event)) appendLiveLog(event);
    });
    refreshTimer = setInterval(loadDashboard, 30000);
  });

  onDestroy(() => {
    if (refreshTimer) clearInterval(refreshTimer);
    closeLiveEvents?.();
  });

  async function loadDashboard() {
    refreshing = true;
    error = '';
    try {
      [connection, telemetry, history] = await Promise.all([
        apiGet<ConnectionStatus>('/connection/status'),
        apiGet<GatewayTelemetry | null>('/telemetry/gateway/latest'),
        apiGet<GatewayTelemetry[]>(`/telemetry/gateway/history?range=${range}&limit=1000`)
      ]);
    } catch (err) {
      error = err instanceof Error ? err.message : 'Dashboard data could not be loaded.';
    } finally {
      loading = false;
      refreshing = false;
    }
  }

  async function loadLiveLog() {
    liveLogError = '';
    try {
      const events = await apiGet<ApiEvent[]>('/system/events?window_seconds=86400&limit=500');
      liveLog = events.filter(isMeshEvent).slice(-liveLogLimit);
    } catch (err) {
      liveLogError = err instanceof Error ? err.message : 'Live log could not be loaded.';
    }
  }

  function loadLiveLogLimit() {
    const saved = Number(localStorage.getItem(liveLogLimitKey));
    if ([25, 50, 100, 200].includes(saved)) {
      liveLogLimit = saved;
    }
  }

  function setLiveLogLimit(nextLimit: number) {
    liveLogLimit = nextLimit;
    localStorage.setItem(liveLogLimitKey, String(nextLimit));
    liveLog = liveLog.slice(-nextLimit);
  }

  function loadLiveLogFilters() {
    const saved = localStorage.getItem(liveLogFiltersKey);
    if (!saved) return;
    try {
      const filters = JSON.parse(saved) as { types?: string[]; sources?: string[]; severities?: string[] };
      liveLogTypes = sanitizeFilterValues(filters.types, liveLogTypeFilters.map((item) => item.value));
      liveLogSources = sanitizeFilterValues(filters.sources, liveLogSourceFilters.map((item) => item.value));
      liveLogSeverities = sanitizeFilterValues(filters.severities, liveLogSeverityFilters.map((item) => item.value));
    } catch {
      saveLiveLogFilters();
    }
  }

  function sanitizeFilterValues(values: string[] | undefined, allowed: string[]) {
    const selected = Array.isArray(values) ? values.filter((value) => allowed.includes(value)) : allowed;
    return selected.length ? selected : allowed;
  }

  function saveLiveLogFilters() {
    localStorage.setItem(
      liveLogFiltersKey,
      JSON.stringify({
        types: liveLogTypes,
        sources: liveLogSources,
        severities: liveLogSeverities
      })
    );
  }

  function toggleLiveLogFilter(group: 'types' | 'sources' | 'severities', value: string) {
    const current = group === 'types' ? liveLogTypes : group === 'sources' ? liveLogSources : liveLogSeverities;
    const next = current.includes(value) ? current.filter((item) => item !== value) : [...current, value];
    if (group === 'types') liveLogTypes = next;
    if (group === 'sources') liveLogSources = next;
    if (group === 'severities') liveLogSeverities = next;
    saveLiveLogFilters();
  }

  function resetLiveLogFilters() {
    liveLogTypes = liveLogTypeFilters.map((item) => item.value);
    liveLogSources = liveLogSourceFilters.map((item) => item.value);
    liveLogSeverities = liveLogSeverityFilters.map((item) => item.value);
    saveLiveLogFilters();
  }

  function liveLogMatchesFilters(event: ApiEvent) {
    const severity = event.severity ?? 'info';
    const source = event.source ?? 'app';
    return liveLogSeverities.includes(severity) && liveLogSources.includes(source) && liveLogTypes.includes(eventCategory(event));
  }

  function isMeshEvent(event: ApiEvent) {
    return event.source === 'meshcore' || meshEventTypes.some((type) => event.type === type || event.type.startsWith(`${type}.`));
  }

  function appendLiveLog(event: ApiEvent) {
    const exists = liveLog.some((item) => event.id && item.id === event.id);
    if (exists) return;
    liveLog = [...liveLog, event].slice(-Math.max(liveLogLimit, 200));
  }

  function loadLayout() {
    const saved = localStorage.getItem(layoutKey);
    if (!saved) return;
    const savedTiles = JSON.parse(saved) as { id: string; size: TileSize }[];
    const byId = new Map(defaultTiles.map((tile) => [tile.id, tile]));
    const restored = savedTiles
      .map((tile) => {
        const source = byId.get(tile.id);
        return source ? { ...source, size: tile.size } : null;
      })
      .filter(Boolean) as DashboardTile[];
    const missing = defaultTiles.filter((tile) => !restored.some((item) => item.id === tile.id));
    tiles = [...restored, ...missing];
  }

  function saveLayout(nextTiles = tiles) {
    localStorage.setItem(layoutKey, JSON.stringify(nextTiles.map(({ id, size }) => ({ id, size }))));
  }

  function loadRange() {
    const saved = localStorage.getItem(rangeKey);
    if (saved && timeRanges.some((item) => item.value === saved)) {
      range = saved;
    }
  }

  function saveRange(nextRange = range) {
    localStorage.setItem(rangeKey, nextRange);
  }

  function moveTile(targetId: string) {
    if (!draggedTileId || draggedTileId === targetId) return;
    const current = [...tiles];
    const from = current.findIndex((tile) => tile.id === draggedTileId);
    const to = current.findIndex((tile) => tile.id === targetId);
    if (from < 0 || to < 0) return;
    const [moved] = current.splice(from, 1);
    current.splice(to, 0, moved);
    tiles = current;
    saveLayout(current);
  }

  function cycleSize(tileId: string) {
    tiles = tiles.map((tile) => {
      if (tile.id !== tileId) return tile;
      const index = sizeOrder.indexOf(tile.size);
      return { ...tile, size: sizeOrder[(index + 1) % sizeOrder.length] };
    });
    saveLayout();
  }

  function metricValue(metric: keyof GatewayTelemetry | undefined, unit = '') {
    if (!metric) return 'Unavailable';
    return displayValue(telemetry?.[metric], unit);
  }

  function tileSubtitle(tile: DashboardTile) {
    if (tile.type === 'chart') return `${history.length} points · ${activeRangeLabel}`;
    if (tile.type === 'device') return connection?.device_identifier ?? 'No device selected';
    return 'Live value';
  }

  async function selectRange(nextRange: string) {
    if (!timeRanges.some((item) => item.value === nextRange)) return;
    range = nextRange;
    saveRange(nextRange);
    await loadDashboard();
  }

  async function sendAdvert() {
    advertSending = true;
    advertStatus = '';
    advertError = '';
    try {
      const result = await apiPost<{ status: string }>('/device/advert');
      advertStatus = result.status === 'sent' ? 'Advert sent.' : 'Advert command accepted.';
    } catch (err) {
      advertError = err instanceof Error ? err.message : 'Advert could not be sent.';
    } finally {
      advertSending = false;
    }
  }

  function tileAccent(tile: DashboardTile) {
    if (tile.id.includes('power') || tile.id === 'battery' || tile.id === 'ch1') return 'power';
    if (tile.id.includes('network') || tile.id === 'nodes' || tile.id === 'signal') return 'network';
    if (tile.id.includes('radio') || tile.id === 'radio') return 'radio';
    if (tile.type === 'device') return connection?.state === 'connected' ? 'connected' : 'attention';
    if (tile.type === 'activity') return 'activity';
    return 'default';
  }

  function tileCategory(tile: DashboardTile) {
    if (tile.type === 'device') return 'Gateway';
    if (tile.id.includes('power') || tile.id === 'battery' || tile.id === 'ch1') return 'Power';
    if (tile.id.includes('network') || tile.id === 'nodes' || tile.id === 'signal') return 'Network';
    if (tile.id.includes('radio') || tile.id === 'radio') return 'Radio';
    return 'Operations';
  }

  function eventTime(value: string) {
    return new Date(value).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  }

  function eventCategory(event: ApiEvent) {
    if (event.type.startsWith('message.')) return 'messages';
    if (event.type === 'meshcore.advertisement' || event.type === 'meshcore.advert_sent' || event.type === 'meshcore.next_contact' || event.type === 'meshcore.contacts') return 'adverts';
    if (event.type.startsWith('telemetry.') || event.type === 'meshcore.stats_packets') return 'telemetry';
    if (event.type.startsWith('node.')) return 'nodes';
    if (event.type.startsWith('automation.')) return 'automations';
    if (event.type.startsWith('connection.')) return 'connection';
    if (event.type.startsWith('system.')) return 'system';
    if (event.type.startsWith('meshcore.')) return 'meshcore';
    return 'system';
  }

  function eventTitle(event: ApiEvent) {
    const payload = normalizedPayload(event);
    if (event.type === 'message.received') return `Message received from ${nodeLabel(payload)}`;
    if (event.type === 'message.sent') return `Message sent to ${nodeLabel(payload)}`;
    if (event.type === 'meshcore.advertisement') return `Advert from ${nodeLabel(payload)}`;
    if (event.type === 'meshcore.advert_sent') return 'Advert sent';
    if (event.type === 'meshcore.next_contact') return `Advert from ${nodeLabel(payload)}`;
    if (event.type === 'meshcore.contacts') return 'Contact list updated';
    if (event.type === 'meshcore.stats_packets') return 'Packet counters updated';
    if (event.type === 'meshcore.device_info') return 'Device info received';
    if (event.type === 'telemetry.gateway_updated') return 'Gateway telemetry updated';
    if (event.type === 'telemetry.node_updated') return `Node telemetry updated for ${nodeLabel(payload)}`;
    if (event.type === 'node.discovered') return `Node discovered: ${nodeLabel(payload)}`;
    if (event.type === 'node.status_changed') return `Node status changed: ${nodeLabel(payload)}`;
    if (event.type === 'automation.completed') return 'Automation completed';
    if (event.type === 'system.error') return String(payload.message ?? 'System error');
    if (event.type.startsWith('meshcore.')) return event.type.replace('meshcore.', 'MeshCore ');
    return event.type;
  }

  function eventDetail(event: ApiEvent) {
    const payload = normalizedPayload(event);
    if (typeof payload.body === 'string' && payload.body.trim()) return payload.body;
    const parts = [
      labelPart('Channel', payload.channel),
      labelPart('Name', payload.adv_name),
      labelPart('Role', payload.role),
      labelPart('Type', payload.type),
      labelPart('Hops', payload.hops),
      labelPart('RX', payload.recv),
      labelPart('TX', payload.sent),
      labelPart('Route', routeLabel(payload.route)),
      labelPart('Battery', payload.battery_percentage),
      labelPart('RSSI', payload.rssi),
      labelPart('SNR', payload.snr)
    ].filter(Boolean);
    if (parts.length) return parts.join(' · ');
    if (payload.message && typeof payload.message === 'string') return payload.message;
    return event.source ?? 'app';
  }

  function nodeLabel(payload: Record<string, unknown>) {
    return String(
      payload.display_name ??
        payload.adv_name ??
        payload.from_node_id ??
        payload.to_node_id ??
        payload.node_id ??
        payload.public_key ??
        'unknown node'
    );
  }

  function normalizedPayload(event: ApiEvent) {
    const payload = event.payload ?? {};
    if (payload.payload && typeof payload.payload === 'object' && !Array.isArray(payload.payload)) {
      return { ...payload, ...(payload.payload as Record<string, unknown>) };
    }
    return payload;
  }

  function labelPart(label: string, value: unknown) {
    if (value === null || value === undefined || value === '') return '';
    return `${label}: ${String(value)}`;
  }

  function routeLabel(value: unknown) {
    if (!value || typeof value !== 'object') return value;
    const route = value as Record<string, unknown>;
    return route.path_display ?? route.path ?? '';
  }

  function rawEventJson(event: ApiEvent) {
    return JSON.stringify(event, null, 2);
  }
</script>

<section class="page dashboard-page">
  <div class="dashboard-hero">
    <div class="hero-copy">
      <div>
        <span class="eyebrow">PacketDeck control room</span>
        <h1>Dashboard</h1>
      </div>
    </div>
    <div class="hero-actions" aria-label="MeshCore actions">
      <button class="advert-button" type="button" onclick={sendAdvert} disabled={advertSending || connection?.state !== 'connected'}>
        {advertSending ? 'Sending...' : 'Advert'}
      </button>
      {#if advertStatus}
        <span class="action-status">{advertStatus}</span>
      {:else if advertError}
        <span class="action-error">{advertError}</span>
      {/if}
    </div>
    <div class="range-panel hero-range" aria-label="Dashboard time range">
      <div>
        <span class="eyebrow">Time range</span>
        <strong>{activeRangeLabel}</strong>
      </div>
      <div class="range-tabs" aria-label="Dashboard time range">
        {#each timeRanges as item}
          <button
            class="range-tab"
            class:active={range === item.value}
            type="button"
            aria-pressed={range === item.value}
            onclick={() => selectRange(item.value)}
          >
            {item.label}
          </button>
        {/each}
      </div>
    </div>
  </div>

  {#if loading}
    <div class="card">Loading dashboard data...</div>
  {:else if error}
    <div class="card error">{error}</div>
  {:else}
    <div class="dashboard-grid" role="list">
      {#each tiles as tile (tile.id)}
        <section
          class="dashboard-tile"
          role="listitem"
          data-size={tile.size}
          data-accent={tileAccent(tile)}
          draggable="true"
          ondragstart={() => (draggedTileId = tile.id)}
          ondragover={(event) => event.preventDefault()}
          ondrop={() => moveTile(tile.id)}
          ondragend={() => (draggedTileId = null)}
          class:dragging={draggedTileId === tile.id}
        >
          <header class="tile-header">
            <div>
              <span class="tile-category">{tileCategory(tile)}</span>
              <h2>{tile.title}</h2>
              <span>{tileSubtitle(tile)}</span>
            </div>
            <div class="tile-actions">
              <button class="tile-tool" type="button" onclick={() => cycleSize(tile.id)}>{tile.size}</button>
            </div>
          </header>

          {#if tile.type === 'device'}
            <div class="tile-values">
              <div><span>Battery voltage</span><strong>{metricValue('battery_voltage_v', 'V')}</strong></div>
              <div><span>Ch1 voltage</span><strong>{metricValue('ch1_voltage_v', 'V')}</strong></div>
              <div><span>Node count</span><strong>{metricValue('node_count')}</strong></div>
              <div><span>Last delivery</span><strong>{metricValue('last_message_delivery')}</strong></div>
            </div>
          {:else if tile.type === 'metric'}
            <div class="metric-tile-body">
              <div class="metric-value">{metricValue(tile.metric, tile.unit)}</div>
              <span>{activeRangeLabel}</span>
            </div>
          {:else if tile.id === 'radio'}
            <div class="tile-values">
              <div><span>Frequency</span><strong>{metricValue('frequency_mhz', 'MHz')}</strong></div>
              <div><span>Bandwidth</span><strong>{metricValue('bandwidth_khz', 'kHz')}</strong></div>
              <div><span>Spreading factor</span><strong>{metricValue('spreading_factor')}</strong></div>
              <div><span>TX power</span><strong>{metricValue('tx_power_dbm', 'dBm')}</strong></div>
            </div>
          {:else if tile.id === 'signal'}
            <div class="tile-values">
              <div><span>RSSI</span><strong>{metricValue('last_rssi', 'dBm')}</strong></div>
              <div><span>SNR</span><strong>{metricValue('last_snr', 'dB')}</strong></div>
              <div><span>Node status</span><strong>{metricValue('node_status')}</strong></div>
              <div><span>Companion prefix</span><strong>{metricValue('companion_prefix')}</strong></div>
            </div>
          {:else if tile.type === 'chart'}
            <div class="embedded-charts">
              {#each tile.charts ?? [] as chart}
                <MetricChart title={chart.title} metric={chart.metric} unit={chart.unit} data={history} embedded />
              {/each}
            </div>
          {:else}
            <div class="tile-values">
              <div><span>Last delivery</span><strong>{metricValue('last_message_delivery')}</strong></div>
              <div><span>Uptime</span><strong>{metricValue('uptime_seconds', 's')}</strong></div>
              <div><span>History range</span><strong>{activeRangeLabel}</strong></div>
            </div>
          {/if}
        </section>
      {/each}
    </div>

    <section class="live-log" aria-label="Mesh live log">
      <header class="live-log-header">
        <div>
          <span class="eyebrow">Mesh live log</span>
          <h2>Live mesh activity</h2>
          <p>{filteredLiveLog.length} matching events · click a row for raw values.</p>
        </div>
        <div class="live-log-actions">
          <select bind:value={liveLogLimit} onchange={(event) => setLiveLogLimit(Number(event.currentTarget.value))} aria-label="Live log window">
            <option value={25}>25 events</option>
            <option value={50}>50 events</option>
            <option value={100}>100 events</option>
            <option value={200}>200 events</option>
          </select>
          <button class="secondary" type="button" onclick={resetLiveLogFilters}>Reset filters</button>
          <button class="secondary" type="button" onclick={loadLiveLog}>Refresh</button>
        </div>
      </header>

      <div class="live-log-filters" aria-label="Live log filters">
        <fieldset>
          <legend>Type</legend>
          {#each liveLogTypeFilters as filter}
            <label>
              <input
                type="checkbox"
                checked={liveLogTypes.includes(filter.value)}
                onchange={() => toggleLiveLogFilter('types', filter.value)}
              />
              <span>{filter.label}</span>
            </label>
          {/each}
        </fieldset>
        <fieldset>
          <legend>Source</legend>
          {#each liveLogSourceFilters as filter}
            <label>
              <input
                type="checkbox"
                checked={liveLogSources.includes(filter.value)}
                onchange={() => toggleLiveLogFilter('sources', filter.value)}
              />
              <span>{filter.label}</span>
            </label>
          {/each}
        </fieldset>
        <fieldset>
          <legend>Severity</legend>
          {#each liveLogSeverityFilters as filter}
            <label>
              <input
                type="checkbox"
                checked={liveLogSeverities.includes(filter.value)}
                onchange={() => toggleLiveLogFilter('severities', filter.value)}
              />
              <span>{filter.label}</span>
            </label>
          {/each}
        </fieldset>
      </div>

      {#if liveLogError}
        <p class="error">{liveLogError}</p>
      {:else if visibleLiveLog.length === 0}
        <p class="muted">No mesh events match the current filters.</p>
      {:else}
        <div class="live-log-list">
          {#each visibleLiveLog as event (event.id ?? `${event.type}-${event.created_at}`)}
            <button
              class="live-log-entry"
              data-severity={event.severity ?? 'info'}
              type="button"
              onclick={() => (selectedLiveLogEvent = event)}
            >
              <time datetime={event.created_at}>{eventTime(event.created_at)}</time>
              <div>
                <strong>{eventTitle(event)}</strong>
                <span>{eventDetail(event)}</span>
              </div>
              <span class="event-meta">
                <span>{eventCategory(event)}</span>
                <code>{event.type}</code>
              </span>
            </button>
          {/each}
        </div>
      {/if}
    </section>
  {/if}

  {#if selectedLiveLogEvent}
    <div
      class="modal-backdrop"
      role="presentation"
      tabindex="-1"
      onclick={(event) => {
        if (event.target === event.currentTarget) selectedLiveLogEvent = null;
      }}
      onkeydown={(event) => {
        if (event.key === 'Escape') selectedLiveLogEvent = null;
      }}
    >
      <div class="raw-event-modal" role="dialog" aria-modal="true" aria-label="Raw live log event">
        <header>
          <div>
            <span class="eyebrow">Raw event</span>
            <h2>{eventTitle(selectedLiveLogEvent)}</h2>
            <p>{selectedLiveLogEvent.type} · {new Date(selectedLiveLogEvent.created_at).toLocaleString()}</p>
          </div>
          <button class="secondary" type="button" onclick={() => (selectedLiveLogEvent = null)}>Close</button>
        </header>
        <pre>{rawEventJson(selectedLiveLogEvent)}</pre>
      </div>
    </div>
  {/if}
</section>

<style>
  .dashboard-page {
    max-width: 1500px;
  }

  .dashboard-hero {
    display: grid;
    grid-template-columns: minmax(12rem, 1fr) auto minmax(24rem, auto);
    align-items: center;
    gap: 1rem;
    border: 1px solid var(--border);
    border-radius: 8px;
    background:
      linear-gradient(135deg, rgba(20, 184, 166, 0.1), transparent 34%),
      linear-gradient(180deg, rgba(16, 24, 39, 0.96), rgba(10, 17, 30, 0.96));
    padding: 1.1rem 1.25rem;
    box-shadow: var(--shadow);
  }

  .hero-copy {
    display: grid;
    gap: 0.55rem;
    min-width: 0;
  }

  .hero-actions {
    display: grid;
    justify-items: center;
    gap: 0.35rem;
    min-width: 7.5rem;
  }

  .advert-button {
    min-width: 7rem;
    min-height: 2.45rem;
    border-color: rgba(20, 184, 166, 0.42);
    background: linear-gradient(135deg, var(--accent), var(--blue));
    color: #04111d;
    font-weight: 900;
    box-shadow: 0 14px 30px rgba(20, 184, 166, 0.18);
  }

  .advert-button:disabled {
    opacity: 0.58;
    cursor: not-allowed;
  }

  .action-status,
  .action-error {
    max-width: 14rem;
    overflow-wrap: anywhere;
    text-align: center;
    font-size: 0.72rem;
    font-weight: 800;
  }

  .action-status {
    color: var(--accent);
  }

  .action-error {
    color: var(--danger);
  }

  .eyebrow {
    color: var(--muted);
    font-size: 0.75rem;
    font-weight: 850;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }

  .dashboard-hero h1 {
    font-size: clamp(1.85rem, 2.4vw, 2.7rem);
    line-height: 1;
  }

  .metric-tile-body span {
    display: block;
    color: var(--muted);
    font-size: 0.78rem;
    font-weight: 750;
  }

  .range-panel {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr) auto;
    align-items: center;
    gap: 1rem;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: rgba(8, 13, 24, 0.7);
    padding: 0.75rem;
  }

  .hero-range {
    grid-template-columns: auto minmax(0, 1fr);
    justify-self: end;
    width: min(100%, 46rem);
    border-color: var(--border);
    background: rgba(8, 13, 24, 0.72);
    box-shadow: none;
  }

  .range-panel > div:first-child {
    display: grid;
    gap: 0.15rem;
    min-width: 8rem;
  }

  .range-panel strong {
    color: var(--text-strong);
    font-size: 0.95rem;
  }

  .range-tabs {
    display: flex;
    flex-wrap: wrap;
    justify-content: center;
    gap: 0.25rem;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: rgba(15, 23, 42, 0.88);
    padding: 0.25rem;
  }

  .range-tab {
    min-height: 2rem;
    border: 0;
    background: transparent;
    padding: 0.35rem 0.65rem;
    color: var(--muted);
    font-size: 0.82rem;
    font-weight: 800;
    white-space: nowrap;
  }

  .range-tab.active {
    background: linear-gradient(135deg, var(--accent), var(--blue));
    color: #04111d;
    box-shadow: 0 12px 26px rgba(20, 184, 166, 0.18);
  }

  .dashboard-grid {
    display: grid;
    grid-template-columns: repeat(12, minmax(0, 1fr));
    gap: 0.9rem;
    align-items: stretch;
  }

  .dashboard-tile {
    position: relative;
    display: grid;
    grid-column: span 3;
    align-content: start;
    gap: 0.9rem;
    min-height: 10rem;
    overflow: hidden;
    border: 1px solid var(--border);
    border-radius: 8px;
    background:
      linear-gradient(180deg, rgba(18, 28, 46, 0.95), rgba(12, 20, 34, 0.95));
    padding: 1rem;
    box-shadow: var(--shadow-soft);
    cursor: grab;
    transition:
      border-color 160ms ease,
      box-shadow 160ms ease,
      transform 160ms ease;
  }

  .dashboard-tile::before {
    content: '';
    position: absolute;
    inset: 0 0 auto 0;
    height: 0.2rem;
    background: var(--muted);
  }

  .dashboard-tile:hover {
    border-color: var(--border-strong);
    box-shadow: 0 22px 54px rgba(0, 0, 0, 0.36);
    transform: translateY(-1px);
  }

  .dashboard-tile[data-accent='connected']::before,
  .dashboard-tile[data-accent='network']::before {
    background: var(--accent);
  }

  .dashboard-tile[data-accent='attention']::before {
    background: var(--danger);
  }

  .dashboard-tile[data-accent='power']::before {
    background: var(--warning);
  }

  .dashboard-tile[data-accent='radio']::before {
    background: var(--blue);
  }

  .dashboard-tile[data-accent='activity']::before {
    background: #94a3b8;
  }

  .dashboard-tile[data-size='medium'] {
    grid-column: span 4;
  }

  .dashboard-tile[data-size='large'] {
    grid-column: span 6;
  }

  .dashboard-tile[data-size='wide'] {
    grid-column: span 12;
  }

  .dashboard-tile.dragging {
    opacity: 0.55;
    transform: scale(0.99);
  }

  .tile-header {
    display: flex;
    justify-content: space-between;
    gap: 1rem;
    align-items: start;
  }

  h2 {
    margin: 0;
    color: var(--text-strong);
    font-size: 1.05rem;
    letter-spacing: 0;
  }

  .tile-header span {
    display: block;
    margin-top: 0.25rem;
    color: var(--muted);
    font-size: 0.82rem;
  }

  .tile-header .tile-category {
    margin: 0 0 0.35rem;
    color: var(--muted);
    font-size: 0.68rem;
    font-weight: 850;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }

  .tile-tool {
    min-height: 1.8rem;
    border-color: transparent;
    background: transparent;
    padding: 0.2rem 0.35rem;
    color: var(--muted);
    font-size: 0.68rem;
    text-transform: uppercase;
  }

  .dashboard-tile:hover .tile-tool,
  .tile-tool:focus-visible {
    border-color: var(--border);
    background: var(--surface-soft);
    color: var(--text);
  }

  .tile-actions {
    display: flex;
    align-items: center;
    gap: 0.45rem;
  }

  .metric-tile-body {
    display: grid;
    align-content: end;
    gap: 0.6rem;
    min-height: 5.8rem;
  }

  .metric-tile-body .metric-value {
    overflow-wrap: anywhere;
    font-size: clamp(1.7rem, 2.8vw, 2.35rem);
    line-height: 1;
  }

  .tile-values {
    display: grid;
    gap: 0.7rem;
  }

  .tile-values div {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    border-top: 1px solid var(--border);
    padding-top: 0.7rem;
  }

  .tile-values div:first-child {
    border-top: 0;
    padding-top: 0;
  }

  .tile-values span {
    color: var(--muted);
    font-size: 0.85rem;
    font-weight: 700;
  }

  .tile-values strong {
    text-align: right;
    overflow-wrap: anywhere;
    color: var(--text-strong);
  }

  .embedded-charts {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(20rem, 1fr));
    gap: 1rem;
  }

  .live-log {
    display: grid;
    gap: 0.85rem;
    border: 1px solid var(--border);
    border-radius: 8px;
    background:
      linear-gradient(135deg, rgba(20, 184, 166, 0.07), transparent 30%),
      linear-gradient(180deg, rgba(18, 28, 46, 0.95), rgba(12, 20, 34, 0.95));
    padding: 0.9rem;
    box-shadow: var(--shadow-soft);
  }

  .live-log-header {
    display: flex;
    align-items: start;
    justify-content: space-between;
    gap: 1rem;
  }

  .live-log-header h2 {
    margin-top: 0.2rem;
  }

  .live-log-header p {
    margin: 0.25rem 0 0;
    color: var(--muted);
    font-size: 0.82rem;
  }

  .live-log-actions {
    display: flex;
    flex-wrap: wrap;
    justify-content: end;
    gap: 0.4rem;
  }

  .live-log-actions select,
  .live-log-actions button {
    min-height: 1.95rem;
    padding: 0.25rem 0.55rem;
    font-size: 0.76rem;
  }

  .live-log-filters {
    display: flex;
    flex-wrap: wrap;
    gap: 0.45rem;
    align-items: start;
  }

  .live-log-filters fieldset {
    display: flex;
    flex-wrap: wrap;
    gap: 0.25rem;
    align-items: center;
    border: 1px solid var(--border);
    border-radius: 999px;
    background: rgba(8, 13, 24, 0.52);
    padding: 0.25rem;
  }

  .live-log-filters legend {
    align-self: center;
    padding: 0 0.35rem 0 0.45rem;
    color: var(--muted);
    font-size: 0.64rem;
    font-weight: 850;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }

  .live-log-filters label {
    display: inline-flex;
    align-items: center;
    gap: 0;
    border: 1px solid var(--border);
    border-radius: 999px;
    background: rgba(15, 23, 42, 0.6);
    padding: 0.18rem 0.42rem;
    color: var(--muted);
    font-size: 0.7rem;
    font-weight: 800;
    white-space: nowrap;
    cursor: pointer;
    transition:
      border-color 140ms ease,
      background 140ms ease,
      color 140ms ease;
  }

  .live-log-filters input {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip: rect(0 0 0 0);
    clip-path: inset(50%);
    white-space: nowrap;
  }

  .live-log-filters label:hover {
    border-color: var(--border-strong);
    color: var(--text);
  }

  .live-log-filters label:has(input:checked) {
    border-color: rgba(20, 184, 166, 0.42);
    background: linear-gradient(135deg, rgba(20, 184, 166, 0.2), rgba(59, 130, 246, 0.12));
    color: var(--text-strong);
  }

  .live-log-list {
    display: grid;
    max-height: 26rem;
    overflow: auto;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: rgba(2, 6, 23, 0.28);
  }

  .live-log-entry {
    position: relative;
    display: grid;
    grid-template-columns: 4.75rem minmax(0, 1fr) minmax(7.5rem, auto);
    gap: 0.75rem;
    align-items: center;
    width: 100%;
    border-top: 1px solid var(--border);
    border-right: 0;
    border-bottom: 0;
    border-left: 0;
    border-radius: 0;
    background: transparent;
    padding: 0.55rem 0.7rem 0.55rem 0.85rem;
    color: inherit;
    text-align: left;
    cursor: pointer;
  }

  .live-log-entry::before {
    content: '';
    position: absolute;
    inset: 0 auto 0 0;
    width: 0.18rem;
    background: rgba(148, 163, 184, 0.52);
  }

  .live-log-entry:first-child {
    border-top: 0;
  }

  .live-log-entry:hover,
  .live-log-entry:focus-visible {
    background: rgba(20, 184, 166, 0.065);
  }

  .live-log-entry time {
    color: var(--muted);
    font-size: 0.72rem;
    font-variant-numeric: tabular-nums;
    font-weight: 800;
  }

  .live-log-entry div {
    display: grid;
    min-width: 0;
    gap: 0.15rem;
  }

  .live-log-entry strong,
  .live-log-entry span {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .live-log-entry strong {
    color: var(--text-strong);
    font-size: 0.86rem;
  }

  .live-log-entry span {
    color: var(--muted);
    font-size: 0.78rem;
  }

  .event-meta {
    display: flex;
    align-items: center;
    justify-content: end;
    gap: 0.35rem;
    min-width: 0;
  }

  .event-meta > span {
    border: 1px solid rgba(20, 184, 166, 0.24);
    border-radius: 999px;
    background: rgba(20, 184, 166, 0.08);
    padding: 0.16rem 0.4rem;
    color: var(--text-strong);
    font-size: 0.64rem;
    font-weight: 850;
    text-transform: capitalize;
  }

  .event-meta code {
    max-width: 11rem;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    border: 1px solid var(--border);
    border-radius: 999px;
    background: rgba(15, 23, 42, 0.78);
    padding: 0.16rem 0.4rem;
    color: var(--muted);
    font-size: 0.64rem;
    font-weight: 800;
  }

  .live-log-entry[data-severity='info']::before {
    background: var(--accent);
  }

  .live-log-entry[data-severity='error'] {
    background: rgba(248, 113, 113, 0.08);
  }

  .live-log-entry[data-severity='error']::before {
    background: var(--danger);
  }

  .live-log-entry[data-severity='warning']::before {
    background: var(--warning);
  }

  .live-log-entry[data-severity='error'] .event-meta code {
    border-color: rgba(248, 113, 113, 0.3);
    color: #fecdd3;
  }

  .modal-backdrop {
    position: fixed;
    inset: 0;
    z-index: 20;
    display: grid;
    place-items: center;
    background: rgba(2, 6, 23, 0.72);
    padding: 1rem;
  }

  .raw-event-modal {
    display: grid;
    gap: 1rem;
    width: min(100%, 64rem);
    max-height: min(82vh, 48rem);
    border: 1px solid var(--border);
    border-radius: 8px;
    background: linear-gradient(180deg, rgba(18, 28, 46, 0.98), rgba(8, 13, 24, 0.98));
    padding: 1rem;
    box-shadow: var(--shadow);
  }

  .raw-event-modal header {
    display: flex;
    align-items: start;
    justify-content: space-between;
    gap: 1rem;
  }

  .raw-event-modal h2 {
    margin-top: 0.25rem;
  }

  .raw-event-modal p {
    margin: 0.35rem 0 0;
    color: var(--muted);
    font-size: 0.88rem;
  }

  .raw-event-modal pre {
    min-height: 0;
    max-height: 34rem;
    overflow: auto;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: rgba(2, 6, 23, 0.72);
    padding: 1rem;
    color: var(--text);
    font-size: 0.82rem;
    line-height: 1.55;
    white-space: pre-wrap;
    word-break: break-word;
  }

  .error {
    color: #fecdd3;
  }

  @media (max-width: 1100px) {
    .dashboard-tile,
    .dashboard-tile[data-size='medium'],
    .dashboard-tile[data-size='large'] {
      grid-column: span 6;
    }
  }

  @media (max-width: 760px) {
    .dashboard-hero {
      align-items: stretch;
      grid-template-columns: 1fr;
    }

    .range-tabs {
      justify-content: start;
      max-width: none;
    }

    .range-panel {
      grid-template-columns: 1fr;
    }

    .hero-range {
      justify-self: stretch;
      width: 100%;
    }

    .dashboard-grid {
      grid-template-columns: 1fr;
    }

    .dashboard-tile,
    .dashboard-tile[data-size='medium'],
    .dashboard-tile[data-size='large'],
    .dashboard-tile[data-size='wide'] {
      grid-column: 1;
    }

    .live-log-header,
    .live-log-entry {
      grid-template-columns: 1fr;
    }

    .live-log-header {
      display: grid;
    }

    .live-log-actions {
      justify-content: start;
    }

    .event-meta {
      justify-content: start;
    }

    .event-meta code {
      justify-self: start;
    }

    .raw-event-modal header {
      display: grid;
    }

  }
</style>
