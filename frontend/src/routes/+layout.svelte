<script lang="ts">
  import { onMount } from 'svelte';
  import { connectEventStream, eventConnectionState } from '$lib/stores/events';
  import { apiGet } from '$lib/api/client';
  import StatusPill from '$lib/components/StatusPill.svelte';
  import type { ConnectionStatus } from '$lib/types/api';
  import type { Snippet } from 'svelte';

  const navItems = [
    ['Dashboard', '/dashboard'],
    ['Messages', '/messages'],
    ['Nodes', '/nodes'],
    ['Map', '/map'],
    ['Device Settings', '/device'],
    ['Automations', '/automations'],
    ['MQTT', '/mqtt'],
    ['System', '/system']
  ];

  let deviceConnection = $state<ConnectionStatus | null>(null);
  let menuOpen = $state(false);
  let connectionTimer: ReturnType<typeof setInterval> | undefined;
  let { children }: { children: Snippet } = $props();

  onMount(() => {
    const closeEvents = connectEventStream();
    refreshConnection();
    connectionTimer = setInterval(refreshConnection, 5000);
    return () => {
      closeEvents();
      if (connectionTimer) clearInterval(connectionTimer);
    };
  });

  async function refreshConnection() {
    try {
      deviceConnection = await apiGet<ConnectionStatus>('/connection/status');
    } catch {
      deviceConnection = null;
    }
  }

  function closeMobileMenu() {
    menuOpen = false;
  }
</script>

<svelte:head>
  <title>PacketDeck</title>
</svelte:head>

<div class="shell">
  <aside class="sidebar" class:menu-open={menuOpen}>
    <div class="sidebar-top">
      <a class="brand" href="/" onclick={closeMobileMenu}>
        <span class="brand-mark">MC</span>
        <span>PacketDeck</span>
      </a>
      <button
        class="menu-toggle"
        type="button"
        aria-label={menuOpen ? 'Close navigation' : 'Open navigation'}
        aria-expanded={menuOpen}
        aria-controls="primary-navigation"
        title={menuOpen ? 'Close navigation' : 'Open navigation'}
        onclick={() => (menuOpen = !menuOpen)}
      >
        <span></span>
        <span></span>
        <span></span>
      </button>
    </div>
    <nav id="primary-navigation">
      {#each navItems as [label, href]}
        <a href={href} onclick={closeMobileMenu}>{label}</a>
      {/each}
    </nav>
    <div class="sidebar-status">
      <div>
        <span>Device connection</span>
        {#if deviceConnection}
          <StatusPill status={deviceConnection.state} />
        {:else}
          <StatusPill status="unknown" />
        {/if}
      </div>
      {#if deviceConnection?.last_error}
        <p>{deviceConnection.last_error}</p>
      {/if}
      <div>
        <span>Backend event stream</span>
        <StatusPill status={$eventConnectionState} />
      </div>
    </div>
  </aside>

  <main>
    {@render children()}
  </main>
</div>

<style>
  :global(*) {
    box-sizing: border-box;
  }

  :global(:root) {
    color-scheme: dark;
    --bg: #070b12;
    --bg-elevated: #0b1220;
    --surface: #101827;
    --surface-strong: #131f33;
    --surface-soft: #0c1422;
    --border: rgba(148, 163, 184, 0.18);
    --border-strong: rgba(148, 163, 184, 0.32);
    --text: #e5edf6;
    --text-strong: #f8fafc;
    --muted: #94a3b8;
    --muted-strong: #cbd5e1;
    --accent: #2dd4bf;
    --accent-strong: #14b8a6;
    --accent-soft: rgba(45, 212, 191, 0.12);
    --danger: #fb7185;
    --danger-soft: rgba(251, 113, 133, 0.12);
    --warning: #facc15;
    --blue: #60a5fa;
    --shadow: 0 18px 48px rgba(0, 0, 0, 0.32);
    --shadow-soft: 0 12px 32px rgba(0, 0, 0, 0.24);
  }

  :global(body) {
    margin: 0;
    min-width: 320px;
    background:
      radial-gradient(circle at 18% 0%, rgba(20, 184, 166, 0.16), transparent 28rem),
      radial-gradient(circle at 92% 12%, rgba(96, 165, 250, 0.12), transparent 26rem),
      linear-gradient(135deg, #050810 0%, var(--bg) 44%, #08111f 100%);
    color: var(--text);
    font-family:
      Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  }

  :global(a) {
    color: inherit;
    text-decoration: none;
  }

  .shell {
    display: grid;
    min-height: 100vh;
    grid-template-columns: 17rem 1fr;
  }

  .sidebar {
    position: sticky;
    top: 0;
    display: flex;
    height: 100vh;
    min-height: 0;
    flex-direction: column;
    gap: 1rem;
    border-right: 1px solid var(--border);
    background: rgba(10, 17, 30, 0.86);
    box-shadow: 18px 0 40px rgba(0, 0, 0, 0.18);
    backdrop-filter: blur(18px);
    padding: 1.25rem;
    overflow: hidden;
  }

  .brand {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    font-weight: 800;
    color: var(--text-strong);
  }

  .brand-mark {
    display: grid;
    width: 2.25rem;
    height: 2.25rem;
    place-items: center;
    border-radius: 8px;
    background: linear-gradient(135deg, var(--accent), var(--blue));
    color: #04111d;
    font-size: 0.85rem;
  }

  .sidebar-top {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
  }

  .menu-toggle {
    display: none;
    width: 2.5rem;
    min-width: 2.5rem;
    height: 2.5rem;
    min-height: 2.5rem;
    align-items: center;
    justify-content: center;
    gap: 0.22rem;
    border-color: var(--border-strong);
    background: var(--surface-soft);
    box-shadow: none;
    padding: 0;
  }

  .menu-toggle span {
    display: block;
    width: 1.05rem;
    height: 2px;
    border-radius: 999px;
    background: var(--text-strong);
  }

  nav {
    display: grid;
    gap: 0.25rem;
    min-height: 0;
    overflow: auto;
  }

  nav a {
    border-radius: 8px;
    padding: 0.62rem 0.75rem;
    color: var(--muted);
    font-weight: 650;
  }

  nav a:hover {
    background: var(--accent-soft);
    color: var(--text-strong);
  }

  .sidebar-status {
    display: grid;
    flex: 0 0 auto;
    gap: 0.6rem;
    margin-top: auto;
    border-top: 1px solid var(--border);
    padding-top: 0.8rem;
    color: var(--muted);
    font-size: 0.9rem;
  }

  .sidebar-status div {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.75rem;
  }

  .sidebar-status p {
    margin: 0;
    border-left: 3px solid var(--danger);
    max-height: 5.4rem;
    overflow: auto;
    padding-left: 0.65rem;
    color: #fecdd3;
    font-size: 0.82rem;
    line-height: 1.35;
  }

  main {
    min-width: 0;
    padding: 1.5rem;
  }

  :global(.page) {
    display: grid;
    gap: 1.25rem;
    max-width: 1280px;
  }

  :global(.page-header) {
    display: flex;
    align-items: end;
    justify-content: space-between;
    gap: 1rem;
  }

  :global(h1) {
    margin: 0;
    font-size: 2rem;
    letter-spacing: 0;
  }

  :global(.muted) {
    color: var(--muted);
  }

  :global(.grid) {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(14rem, 1fr));
    gap: 1rem;
  }

  :global(.card) {
    border: 1px solid var(--border);
    border-radius: 8px;
    background: linear-gradient(180deg, rgba(16, 24, 39, 0.96), rgba(12, 20, 34, 0.96));
    padding: 1rem;
    box-shadow: var(--shadow-soft);
  }

  :global(.metric-label) {
    color: var(--muted);
    font-size: 0.85rem;
    font-weight: 700;
  }

  :global(.metric-value) {
    margin-top: 0.4rem;
    font-size: 1.55rem;
    font-weight: 800;
  }

  :global(table) {
    width: 100%;
    border-collapse: collapse;
    overflow: hidden;
    border-radius: 8px;
    background: var(--surface);
  }

  :global(th),
  :global(td) {
    border-bottom: 1px solid var(--border);
    padding: 0.85rem;
    text-align: left;
  }

  :global(th) {
    color: var(--muted);
    font-size: 0.8rem;
    text-transform: uppercase;
  }

  :global(button),
  :global(input),
  :global(select),
  :global(textarea) {
    min-height: 2.5rem;
    border: 1px solid var(--border-strong);
    border-radius: 8px;
    background: var(--surface-soft);
    color: var(--text);
    padding: 0.6rem 0.75rem;
    font: inherit;
  }

  :global(input::placeholder),
  :global(textarea::placeholder) {
    color: var(--muted);
  }

  :global(button) {
    border-color: rgba(45, 212, 191, 0.5);
    background: linear-gradient(135deg, #14b8a6, #38bdf8);
    color: #04111d;
    font-weight: 750;
    cursor: pointer;
    box-shadow: 0 10px 24px rgba(20, 184, 166, 0.16);
  }

  :global(button.secondary) {
    border-color: var(--border-strong);
    background: var(--surface-soft);
    color: var(--text);
    box-shadow: none;
  }

  @media (max-width: 820px) {
    .shell {
      grid-template-columns: 1fr;
    }

    .sidebar {
      position: sticky;
      top: 0;
      z-index: 10;
      height: auto;
      max-height: 100vh;
      gap: 0;
      border-right: 0;
      border-bottom: 1px solid var(--border);
      overflow: auto;
      padding: 0.9rem 1rem;
    }

    .menu-toggle {
      display: inline-flex;
      flex-direction: column;
    }

    nav {
      display: none;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      margin-top: 0.9rem;
    }

    .sidebar.menu-open nav,
    .sidebar.menu-open .sidebar-status {
      display: grid;
    }

    .sidebar-status {
      display: none;
      margin-top: 0.9rem;
    }

    main {
      padding: 1rem;
    }
  }
</style>
