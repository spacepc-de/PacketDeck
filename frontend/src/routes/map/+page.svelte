<script lang="ts">
  import { onDestroy, onMount, tick } from 'svelte';
  import { apiGet } from '$lib/api/client';
  import { displayDate, displayValue } from '$lib/utils/format';
  import type { NodeSummary } from '$lib/types/api';

  let nodes = $state<NodeSummary[]>([]);
  let mapElement = $state<HTMLDivElement | null>(null);
  let mapState = $state<'idle' | 'loading' | 'ready' | 'error'>('idle');
  let mapError = $state('');
  let error = $state('');
  let map: any = null;
  let markerLayer: any = null;
  let leafletPromise: Promise<any> | null = null;
  const nodesWithCoordinates = $derived(nodes.filter(hasCoordinates));

  onMount(async () => {
    await tick();
    await initializeMap();
    await loadNodes();
  });

  onDestroy(() => {
    if (map) {
      map.remove();
      map = null;
      markerLayer = null;
    }
  });

  async function loadNodes() {
    try {
      error = '';
      nodes = await apiGet<NodeSummary[]>('/nodes');
      await tick();
      await initializeMap();
      updateMapMarkers();
    } catch (err) {
      error = err instanceof Error ? err.message : 'Nodes could not be loaded.';
    }
  }

  function nodeName(node: NodeSummary) {
    return node.display_name ?? node.short_name ?? node.meshcore_id;
  }

  function numericValue(value: unknown) {
    const parsed = typeof value === 'number' ? value : Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }

  function nodeLatitude(node: NodeSummary) {
    return numericValue(node.latitude ?? node.raw_info?.contact?.adv_lat);
  }

  function nodeLongitude(node: NodeSummary) {
    return numericValue(node.longitude ?? node.raw_info?.contact?.adv_lon);
  }

  function hasCoordinates(node: NodeSummary) {
    const latitude = nodeLatitude(node);
    const longitude = nodeLongitude(node);
    if (latitude === null || longitude === null) return false;
    if (latitude === 0 && longitude === 0) return false;
    return latitude >= -90 && latitude <= 90 && longitude >= -180 && longitude <= 180;
  }

  async function loadLeaflet() {
    if (typeof window === 'undefined') return null;
    const existing = (window as any).L;
    if (existing) return existing;
    if (!leafletPromise) {
      leafletPromise = new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';
        script.integrity = 'sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=';
        script.crossOrigin = '';
        script.onload = () => resolve((window as any).L);
        script.onerror = () => reject(new Error('OpenStreetMap library could not be loaded.'));
        document.head.appendChild(script);
      });
    }
    return leafletPromise;
  }

  async function initializeMap() {
    if (!mapElement || map) return;
    mapState = 'loading';
    mapError = '';
    try {
      const L = await loadLeaflet();
      if (!L || !mapElement) return;
      map = L.map(mapElement, {
        boxZoom: true,
        doubleClickZoom: true,
        dragging: true,
        keyboard: true,
        scrollWheelZoom: true,
        tap: true,
        touchZoom: true,
        zoomControl: true
      }).setView([51.1657, 10.4515], 5);
      const tileLayer = L.tileLayer(
        'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
        {
          crossOrigin: true,
          detectRetina: true,
          keepBuffer: 4,
          maxZoom: 19,
          subdomains: ['a', 'b', 'c'],
          tileSize: 256,
          updateWhenIdle: false,
          updateWhenZooming: true,
          attribution: '&copy; OpenStreetMap contributors'
        }
      );
      tileLayer.on('tileerror', (event: any) => {
        const tile = event?.tile as HTMLImageElement | undefined;
        const coords = event?.coords;
        if (!tile || !coords || tile.dataset.fallback === 'openstreetmap-de') return;
        tile.dataset.fallback = 'openstreetmap-de';
        tile.src = `https://tile.openstreetmap.de/${coords.z}/${coords.x}/${coords.y}.png`;
      });
      tileLayer.addTo(map);
      markerLayer = L.layerGroup().addTo(map);
      mapState = 'ready';
      setTimeout(() => map?.invalidateSize(), 0);
      setTimeout(() => map?.invalidateSize(), 250);
    } catch (err) {
      mapState = 'error';
      mapError = err instanceof Error ? err.message : 'OpenStreetMap could not be loaded.';
    }
  }

  function updateMapMarkers() {
    if (!map || !markerLayer) return;
    const L = (window as any).L;
    markerLayer.clearLayers();
    const bounds: [number, number][] = [];
    for (const node of nodesWithCoordinates) {
      const latitude = nodeLatitude(node);
      const longitude = nodeLongitude(node);
      if (latitude === null || longitude === null) continue;
      bounds.push([latitude, longitude]);
      const markerIcon = L.divIcon({
        className: 'node-map-marker',
        html: nodeMarkerHtml(node),
        iconSize: [34, 34],
        iconAnchor: [17, 17],
        popupAnchor: [0, -18],
        tooltipAnchor: [0, -20]
      });
      L.marker([latitude, longitude], { icon: markerIcon, title: nodeName(node) })
        .bindTooltip(nodeTooltipHtml(node), {
          className: 'node-map-tooltip',
          direction: 'top',
          opacity: 1,
          sticky: true
        })
        .bindPopup(nodePopupHtml(node))
        .addTo(markerLayer);
    }
    if (bounds.length === 1) {
      map.setView(bounds[0], 12);
    } else if (bounds.length > 1) {
      map.fitBounds(bounds, { padding: [32, 32], maxZoom: 13 });
    }
    setTimeout(() => map?.invalidateSize(), 0);
  }

  function escapeHtml(value: unknown) {
    return String(value)
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#039;');
  }

  function markerStatusClass(node: NodeSummary) {
    const status = String(node.status ?? 'unknown').toLowerCase();
    if (status === 'online') return 'online';
    if (status === 'offline') return 'offline';
    return 'unknown';
  }

  function nodeBatteryLabel(node: NodeSummary) {
    if (node.battery_voltage_v !== null && node.battery_voltage_v !== undefined) {
      return displayValue(node.battery_voltage_v, 'V');
    }
    if (node.battery_percentage !== null && node.battery_percentage !== undefined) {
      return displayValue(node.battery_percentage, '%');
    }
    return 'Unavailable';
  }

  function nodeMarkerHtml(node: NodeSummary) {
    return `<span class="node-marker node-marker-${markerStatusClass(node)}" aria-hidden="true"><span></span></span>`;
  }

  function nodeTooltipHtml(node: NodeSummary) {
    const latitude = nodeLatitude(node);
    const longitude = nodeLongitude(node);
    return `
      <div class="node-info-card">
        <strong>${escapeHtml(nodeName(node))}</strong>
        <span>${escapeHtml(node.role ?? 'Unknown')} · ${escapeHtml(node.status ?? 'unknown')}</span>
        <dl>
          <div><dt>Battery</dt><dd>${escapeHtml(nodeBatteryLabel(node))}</dd></div>
          <div><dt>Last heard</dt><dd>${escapeHtml(displayDate(node.last_heard_at))}</dd></div>
          <div><dt>Position</dt><dd>${escapeHtml(formatCoordinate(latitude))}, ${escapeHtml(formatCoordinate(longitude))}</dd></div>
        </dl>
      </div>
    `;
  }

  function nodePopupHtml(node: NodeSummary) {
    return `<strong>${escapeHtml(nodeName(node))}</strong><br>${escapeHtml(node.role ?? 'Unknown')} · ${escapeHtml(node.status ?? 'unknown')}<br>Battery: ${escapeHtml(nodeBatteryLabel(node))}<br>Last heard: ${escapeHtml(displayDate(node.last_heard_at))}`;
  }

  function formatCoordinate(value: number | null) {
    return value === null ? 'Unavailable' : value.toFixed(5);
  }
</script>

<svelte:head>
  <link
    rel="stylesheet"
    href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
    integrity="sha256-p4NxAoJBhIINfQ7I2nLMg0w5IJiZVFq9N6P4h7eWwHk="
    crossorigin=""
  />
</svelte:head>

<section class="map-page">
  <div class="map-frame">
    <div class="node-map" bind:this={mapElement}></div>

    <div class="map-controls">
      <span>{nodesWithCoordinates.length} / {nodes.length} nodes</span>
      <button onclick={loadNodes}>Refresh</button>
    </div>

    {#if error}
      <div class="map-overlay error top">{error}</div>
    {:else if mapState === 'loading'}
      <div class="map-overlay">Loading OpenStreetMap...</div>
    {:else if mapState === 'error'}
      <div class="map-overlay error">{mapError}</div>
    {:else if nodesWithCoordinates.length === 0}
      <div class="map-overlay">No node coordinates are available yet.</div>
    {/if}
  </div>
</section>

<style>
  :global(main:has(.map-page)) {
    padding: 0;
    overflow: hidden;
  }

  .map-page {
    position: relative;
    display: block;
    width: 100%;
    height: 100vh;
    max-width: none;
    min-height: 0;
    overflow: hidden;
  }

  .map-frame {
    position: relative;
    width: 100%;
    height: 100%;
    min-height: 0;
    overflow: hidden;
    background: rgba(2, 6, 23, 0.34);
    isolation: isolate;
  }

  .node-map {
    position: absolute;
    inset: 0;
    z-index: 0;
  }

  .map-controls {
    position: absolute;
    top: 1rem;
    right: 1rem;
    z-index: 3;
    display: flex;
    align-items: center;
    gap: 0.6rem;
  }

  .map-controls span {
    border: 1px solid rgba(15, 23, 42, 0.18);
    border-radius: 8px;
    background: rgba(248, 250, 252, 0.92);
    box-shadow: 0 12px 32px rgba(15, 23, 42, 0.22);
    color: #0f172a;
    padding: 0.58rem 0.72rem;
    font-size: 0.78rem;
    font-weight: 850;
    white-space: nowrap;
  }

  .map-controls button {
    border-color: rgba(15, 23, 42, 0.18);
    background: rgba(248, 250, 252, 0.94);
    box-shadow: 0 12px 32px rgba(15, 23, 42, 0.22);
    color: #0f172a;
  }

  .map-controls button:hover {
    background: #ffffff;
  }

  .map-overlay {
    pointer-events: none;
    position: absolute;
    inset: auto 1rem 1rem 1rem;
    z-index: 2;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: rgba(8, 13, 24, 0.88);
    padding: 0.75rem 0.9rem;
    color: var(--muted);
    font-size: 0.88rem;
    font-weight: 750;
    backdrop-filter: blur(10px);
  }

  .map-overlay.top {
    inset: 1rem auto auto 1rem;
    max-width: min(34rem, calc(100% - 2rem));
  }

  .map-overlay.error {
    border-color: rgba(248, 113, 113, 0.42);
    background: rgba(248, 113, 113, 0.12);
    color: #fecaca;
  }

  :global(.leaflet-container) {
    background: #0f172a;
    color: #0f172a;
    font-family: inherit;
  }

  :global(.leaflet-tile) {
    border: 0 !important;
    max-width: none !important;
    max-height: none !important;
  }

  :global(.leaflet-pane),
  :global(.leaflet-tile),
  :global(.leaflet-marker-icon),
  :global(.leaflet-marker-shadow),
  :global(.leaflet-tile-container),
  :global(.leaflet-pane > svg),
  :global(.leaflet-pane > canvas),
  :global(.leaflet-zoom-box),
  :global(.leaflet-image-layer),
  :global(.leaflet-layer) {
    position: absolute;
    left: 0;
    top: 0;
  }

  :global(.leaflet-control-container .leaflet-top),
  :global(.leaflet-control-container .leaflet-bottom) {
    position: absolute;
    z-index: 1000;
    pointer-events: none;
  }

  :global(.leaflet-control) {
    pointer-events: auto;
  }

  :global(.leaflet-tile-pane) {
    z-index: 200;
  }

  :global(.leaflet-overlay-pane) {
    z-index: 400;
  }

  :global(.leaflet-shadow-pane) {
    z-index: 500;
  }

  :global(.leaflet-marker-pane) {
    z-index: 600;
  }

  :global(.leaflet-tooltip-pane) {
    z-index: 850;
  }

  :global(.leaflet-popup-pane) {
    z-index: 900;
  }

  :global(.leaflet-popup-content-wrapper),
  :global(.leaflet-popup-tip) {
    background: #0f172a;
    color: #e5edf7;
    border: 1px solid rgba(148, 163, 184, 0.25);
    box-shadow: 0 18px 40px rgba(0, 0, 0, 0.35);
  }

  :global(.leaflet-popup-content) {
    margin: 0.65rem 0.75rem;
    color: #cbd5e1;
    line-height: 1.45;
  }

  :global(.leaflet-popup-content strong) {
    color: #f8fafc;
  }

  :global(.node-map-marker) {
    display: grid;
    place-items: center;
    background: transparent;
    border: 0;
  }

  :global(.node-marker) {
    position: relative;
    display: grid;
    width: 34px;
    height: 34px;
    place-items: center;
    border-radius: 999px;
    background: rgba(8, 13, 24, 0.82);
    border: 1px solid rgba(226, 232, 240, 0.48);
    box-shadow:
      0 12px 26px rgba(0, 0, 0, 0.38),
      0 0 0 5px rgba(14, 165, 233, 0.12);
  }

  :global(.node-marker::after) {
    content: '';
    position: absolute;
    bottom: -5px;
    width: 11px;
    height: 11px;
    transform: rotate(45deg);
    border-right: 1px solid rgba(226, 232, 240, 0.48);
    border-bottom: 1px solid rgba(226, 232, 240, 0.48);
    background: rgba(8, 13, 24, 0.82);
  }

  :global(.node-marker span) {
    position: relative;
    z-index: 1;
    width: 13px;
    height: 13px;
    border-radius: 999px;
    background: #94a3b8;
    box-shadow: 0 0 0 4px rgba(148, 163, 184, 0.18);
  }

  :global(.node-marker-online span) {
    background: #22c55e;
    box-shadow: 0 0 0 4px rgba(34, 197, 94, 0.2);
  }

  :global(.node-marker-offline span) {
    background: #ef4444;
    box-shadow: 0 0 0 4px rgba(239, 68, 68, 0.18);
  }

  :global(.node-marker-unknown span) {
    background: #f59e0b;
    box-shadow: 0 0 0 4px rgba(245, 158, 11, 0.18);
  }

  :global(.node-map-tooltip) {
    padding: 0;
    border: 0;
    background: transparent;
    box-shadow: none;
    z-index: 850;
  }

  :global(.node-map-tooltip::before) {
    display: none;
  }

  :global(.node-info-card) {
    display: grid;
    min-width: 220px;
    gap: 0.45rem;
    border: 1px solid rgba(148, 163, 184, 0.26);
    border-radius: 8px;
    background: rgba(8, 13, 24, 0.94);
    padding: 0.72rem 0.78rem;
    color: #cbd5e1;
    box-shadow: 0 18px 42px rgba(0, 0, 0, 0.36);
    backdrop-filter: blur(12px);
  }

  :global(.node-info-card strong) {
    color: #f8fafc;
    font-size: 0.9rem;
    line-height: 1.15;
  }

  :global(.node-info-card > span) {
    color: #94a3b8;
    font-size: 0.76rem;
    font-weight: 750;
  }

  :global(.node-info-card dl) {
    display: grid;
    gap: 0.3rem;
    margin: 0;
  }

  :global(.node-info-card dl div) {
    display: flex;
    justify-content: space-between;
    gap: 0.75rem;
  }

  :global(.node-info-card dt) {
    color: #94a3b8;
    font-size: 0.72rem;
    font-weight: 800;
  }

  :global(.node-info-card dd) {
    margin: 0;
    color: #e2e8f0;
    font-size: 0.72rem;
    font-weight: 800;
    text-align: right;
  }

  :global(.leaflet-control-attribution) {
    background: rgba(15, 23, 42, 0.78) !important;
    color: #cbd5e1 !important;
    font-size: 0.68rem;
  }

  :global(.leaflet-control-attribution a) {
    color: #67e8f9 !important;
  }

  @media (max-width: 820px) {
    :global(main:has(.map-page)) {
      padding: 0;
    }

    .map-page {
      height: calc(100vh - 8.5rem);
    }

    .map-controls {
      right: 0.75rem;
      left: 0.75rem;
      justify-content: flex-end;
      flex-wrap: wrap;
    }
  }
</style>
