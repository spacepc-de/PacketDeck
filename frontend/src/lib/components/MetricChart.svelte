<script lang="ts">
  import { displayValue } from '$lib/utils/format';

  type Point = { recorded_at?: string; [key: string]: unknown };
  type ChartPoint = { x: number; y: number };
  type ChartValue = { time: number; value: number };

  let {
    title,
    unit = '',
    metric,
    data = [],
    embedded = false
  }: {
    title: string;
    unit?: string;
    metric: string;
    data: Point[];
    embedded?: boolean;
  } = $props();

  const values = $derived(
    data
      .map((point) => toChartValue(point))
      .filter((point): point is ChartValue => point !== null)
  );
  const latest = $derived(values.at(-1)?.value);
  const min = $derived(values.length ? Math.min(...values.map((point) => point.value)) : 0);
  const max = $derived(values.length ? Math.max(...values.map((point) => point.value)) : 0);
  const path = $derived(chartPath(values, min, max));
  const latestPoint = $derived(pointPosition(values.at(-1), values, min, max));
  const gradientId = $derived(`chart-area-${metric}-${title}`.replace(/[^a-zA-Z0-9_-]/g, '-'));
  let hover = $state<(ChartValue & ChartPoint) | null>(null);

  function toChartValue(point: Point): ChartValue | null {
    const rawValue = point[metric];
    if (rawValue === null || rawValue === undefined || rawValue === '') return null;
    const time = point.recorded_at ? new Date(point.recorded_at).getTime() : 0;
    const value = Number(rawValue);
    if (!Number.isFinite(value) || time <= 0) return null;
    return { time, value };
  }

  function chartPath(points: ChartValue[], minValue: number, maxValue: number) {
    const chartPoints = normalizePoints(points, minValue, maxValue);
    if (chartPoints.length === 0) return '';
    if (chartPoints.length === 1) return `M ${chartPoints[0].x.toFixed(2)} ${chartPoints[0].y.toFixed(2)}`;

    const segments = [`M ${chartPoints[0].x.toFixed(2)} ${chartPoints[0].y.toFixed(2)}`];
    const tension = 0.28;
    for (let index = 0; index < chartPoints.length - 1; index += 1) {
      const start = chartPoints[index];
      const end = chartPoints[index + 1];
      const previous = chartPoints[index - 1] ?? start;
      const next = chartPoints[index + 2] ?? end;
      const firstControl = {
        x: start.x + (end.x - previous.x) * tension,
        y: start.y + (end.y - previous.y) * tension
      };
      const secondControl = {
        x: end.x - (next.x - start.x) * tension,
        y: end.y - (next.y - start.y) * tension
      };
      segments.push(
        [
          'C',
          clamp(firstControl.x, start.x, end.x).toFixed(2),
          clamp(firstControl.y, 4, 38).toFixed(2),
          clamp(secondControl.x, start.x, end.x).toFixed(2),
          clamp(secondControl.y, 4, 38).toFixed(2),
          end.x.toFixed(2),
          end.y.toFixed(2)
        ].join(' ')
      );
    }
    return segments.join(' ');
  }

  function normalizePoints(
    points: ChartValue[],
    minValue: number,
    maxValue: number
  ): ChartPoint[] {
    if (points.length === 0) return [];
    const minTime = points[0].time;
    const maxTime = points.at(-1)?.time ?? minTime;
    const timeSpan = Math.max(maxTime - minTime, 1);
    const valueSpan = Math.max(maxValue - minValue, 1);
    return points.map((point) => ({
      x: ((point.time - minTime) / timeSpan) * 100,
      y: 36 - ((point.value - minValue) / valueSpan) * 30
    }));
  }

  function clamp(value: number, minValue: number, maxValue: number) {
    return Math.min(Math.max(value, minValue), maxValue);
  }

  function pointPosition(
    point: ChartValue | undefined,
    points: ChartValue[],
    minValue: number,
    maxValue: number
  ) {
    if (!point || points.length === 0) return null;
    const minTime = points[0].time;
    const maxTime = points.at(-1)?.time ?? minTime;
    const timeSpan = Math.max(maxTime - minTime, 1);
    const valueSpan = Math.max(maxValue - minValue, 1);
    return {
      x: ((point.time - minTime) / timeSpan) * 100,
      y: 36 - ((point.value - minValue) / valueSpan) * 30
    };
  }

  function handlePointerMove(event: PointerEvent) {
    const svg = event.currentTarget as SVGSVGElement;
    const bounds = svg.getBoundingClientRect();
    const pointerX = clamp(((event.clientX - bounds.left) / Math.max(bounds.width, 1)) * 100, 0, 100);
    let nearest: (ChartValue & ChartPoint) | null = null;
    for (const point of values) {
      const position = pointPosition(point, values, min, max);
      if (!position) continue;
      const candidate = { ...point, ...position };
      if (!nearest || Math.abs(candidate.x - pointerX) < Math.abs(nearest.x - pointerX)) {
        nearest = candidate;
      }
    }
    hover = nearest;
  }

  function handlePointerLeave() {
    hover = null;
  }

  function tooltipX(point: ChartPoint) {
    return clamp(point.x, 18, 82);
  }

  function tooltipTime(time: number) {
    return new Intl.DateTimeFormat(undefined, {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    }).format(new Date(time));
  }
</script>

<section class="chart-card" class:embedded>
  <header>
    <div>
      <h3>{title}</h3>
      <span>{values.length} points</span>
    </div>
    <strong>{displayValue(latest, unit)}</strong>
  </header>

  {#if values.length < 2}
    <div class="empty">Not enough history yet.</div>
  {:else}
    <svg
      viewBox="0 0 100 40"
      preserveAspectRatio="none"
      aria-label={title}
      role="img"
      onpointermove={handlePointerMove}
      onpointerleave={handlePointerLeave}
    >
      <defs>
        <linearGradient id={gradientId} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stop-color="#2dd4bf" stop-opacity="0.28" />
          <stop offset="100%" stop-color="#2dd4bf" stop-opacity="0.03" />
        </linearGradient>
      </defs>
      <line class="grid-line" x1="0" x2="100" y1="10" y2="10" />
      <line class="grid-line" x1="0" x2="100" y1="22" y2="22" />
      <line class="grid-line" x1="0" x2="100" y1="34" y2="34" />
      <path class="area" d={`${path} L 100 40 L 0 40 Z`} fill={`url(#${gradientId})`} />
      <path class="line" d={path} />
      {#if hover}
        <line class="hover-line" x1={hover.x} x2={hover.x} y1="4" y2="38" />
        <circle class="hover-point" cx={hover.x} cy={hover.y} r="2" />
        <g class="tooltip" transform={`translate(${tooltipX(hover)} 2)`}>
          <rect x="-17" y="0" width="34" height="10" rx="2" />
          <text x="0" y="4.1">{displayValue(hover.value, unit)}</text>
          <text x="0" y="8.2">{tooltipTime(hover.time)}</text>
        </g>
      {/if}
      {#if latestPoint}
        <circle class="endpoint" cx={latestPoint.x} cy={latestPoint.y} r="1.7" />
      {/if}
    </svg>
  {/if}
</section>

<style>
  .chart-card {
    display: grid;
    gap: 0.8rem;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: var(--surface);
    padding: 1rem;
    min-width: 0;
  }

  .chart-card.embedded {
    border: 0;
    background: transparent;
    padding: 0;
  }

  header {
    display: flex;
    justify-content: space-between;
    gap: 1rem;
    min-width: 0;
  }

  h3 {
    margin: 0;
    color: var(--text-strong);
    font-size: 0.95rem;
  }

  span {
    color: var(--muted);
    font-size: 0.8rem;
  }

  strong {
    white-space: nowrap;
    color: var(--text-strong);
    font-size: 0.92rem;
  }

  svg {
    width: 100%;
    height: 10rem;
    overflow: visible;
    touch-action: none;
  }

  .line {
    fill: none;
    stroke: var(--accent);
    stroke-width: 2.2;
    stroke-linecap: round;
    stroke-linejoin: round;
    vector-effect: non-scaling-stroke;
  }

  .area {
    opacity: 1;
  }

  .grid-line {
    stroke: rgba(148, 163, 184, 0.18);
    stroke-width: 0.8;
    vector-effect: non-scaling-stroke;
  }

  .endpoint {
    fill: var(--surface);
    stroke: var(--accent);
    stroke-width: 1.6;
    vector-effect: non-scaling-stroke;
  }

  .hover-line {
    stroke: rgba(226, 232, 240, 0.52);
    stroke-dasharray: 2 2;
    stroke-width: 0.8;
    vector-effect: non-scaling-stroke;
  }

  .hover-point {
    fill: #04111d;
    stroke: var(--accent);
    stroke-width: 1.8;
    vector-effect: non-scaling-stroke;
  }

  .tooltip rect {
    fill: rgba(3, 7, 18, 0.92);
    stroke: rgba(45, 212, 191, 0.42);
    stroke-width: 0.6;
    vector-effect: non-scaling-stroke;
  }

  .tooltip text {
    fill: var(--text-strong);
    font-size: 2.2px;
    font-weight: 800;
    text-anchor: middle;
    dominant-baseline: middle;
    vector-effect: non-scaling-stroke;
  }

  .tooltip text + text {
    fill: var(--muted);
    font-size: 1.8px;
    font-weight: 700;
  }

  .empty {
    display: grid;
    min-height: 10rem;
    place-items: center;
    border: 1px dashed var(--border-strong);
    border-radius: 8px;
    background: var(--surface-soft);
    color: var(--muted);
    font-size: 0.9rem;
  }
</style>
