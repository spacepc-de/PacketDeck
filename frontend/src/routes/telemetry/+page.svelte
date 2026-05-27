<script lang="ts">
  import { onMount } from 'svelte';
  import MetricChart from '$lib/components/MetricChart.svelte';
  import { apiGet } from '$lib/api/client';
  import { displayValue } from '$lib/utils/format';
  import type { GatewayTelemetry } from '$lib/types/api';

  let latest = $state<GatewayTelemetry | null>(null);
  let history = $state<GatewayTelemetry[]>([]);
  let range = $state('24h');
  const hasBatteryPercentage = $derived(
    hasMetricValue(latest?.battery_percentage) || history.some((item) => hasMetricValue(item.battery_percentage))
  );
  const metrics = $derived([
    ...(hasBatteryPercentage ? [['Battery percentage', displayValue(latest?.battery_percentage, '%')]] : []),
    ['Battery voltage', displayValue(latest?.battery_voltage_v, 'V')],
    ['Ch1 voltage', displayValue(latest?.ch1_voltage_v, 'V')],
    ['Node count', displayValue(latest?.node_count)],
    ['Rate limiter', displayValue(latest?.request_rate_limiter_tokens, 'tokens')],
    ['Frequency', displayValue(latest?.frequency_mhz, 'MHz')],
    ['TX power', displayValue(latest?.tx_power_dbm, 'dBm')]
  ]);

  onMount(async () => {
    await loadTelemetry();
  });

  async function loadTelemetry() {
    [latest, history] = await Promise.all([
      apiGet<GatewayTelemetry | null>('/telemetry/gateway/latest'),
      apiGet<GatewayTelemetry[]>(`/telemetry/gateway/history?range=${range}&limit=1000`)
    ]);
  }

  function hasMetricValue(value: unknown) {
    return value !== null && value !== undefined && value !== '';
  }
</script>

<section class="page">
  <div class="page-header">
    <div>
      <h1>Telemetry</h1>
      <p class="muted">Gateway and node telemetry history with export-ready data.</p>
    </div>
    <select bind:value={range} onchange={loadTelemetry} aria-label="Time range">
      <option value="1h">Last hour</option>
      <option value="24h">Last 24 hours</option>
      <option value="7d">Last 7 days</option>
      <option value="30d">Last 30 days</option>
    </select>
  </div>

  <div class="grid">
    {#each metrics as [label, value]}
      <div class="card">
        <div class="metric-label">{label}</div>
        <div class="metric-value">{value}</div>
      </div>
    {/each}
  </div>

  <section class="history-section">
    <h2>Gateway History</h2>
    <p class="muted">{history.length} telemetry records loaded.</p>
    <div class="chart-grid">
      {#if hasBatteryPercentage}
        <MetricChart title="Battery percentage" metric="battery_percentage" unit="%" data={history} />
      {/if}
      <MetricChart title="Battery voltage" metric="battery_voltage_v" unit="V" data={history} />
      <MetricChart title="Ch1 voltage" metric="ch1_voltage_v" unit="V" data={history} />
      <MetricChart title="Node count" metric="node_count" data={history} />
      <MetricChart title="Rate limiter" metric="request_rate_limiter_tokens" unit="tokens" data={history} />
      <MetricChart title="Frequency" metric="frequency_mhz" unit="MHz" data={history} />
      <MetricChart title="TX power" metric="tx_power_dbm" unit="dBm" data={history} />
      <MetricChart title="SNR" metric="last_snr" unit="dB" data={history} />
    </div>
  </section>
</section>

<style>
  h2 {
    margin: 0 0 0.5rem;
  }

  .history-section {
    display: grid;
    gap: 0.75rem;
    margin-top: 1rem;
  }

  .chart-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(16rem, 1fr));
    gap: 1rem;
  }
</style>
