<script lang="ts">
  import { apiGet, apiPost } from '$lib/api/client';
  import { tick } from 'svelte';
  import { onDestroy, onMount } from 'svelte';

  type ConversationTarget = {
    id: string;
    type: 'node' | 'channel';
    label: string;
    detail: string;
    toNodeId: string | null;
    channel: string | null;
    isFavorite?: boolean;
    lastMessage?: string | null;
    lastAt?: string | null;
    duplicate_public_key_prefix?: string | null;
    warning?: string | null;
    duplicate_nodes?: Array<{ id: string; label?: string | null; public_key?: string | null; meshcore_id?: string | null }>;
  };

  type DebugEvent = {
    id: string;
    type: string;
    source: string;
    severity: string;
    meshcore_event_type: string | null;
    payload: Record<string, unknown>;
    created_at: string;
  };

  let messages = $state<any[]>([]);
  let targets = $state<ConversationTarget[]>([]);
  let selectedTargetId = $state('');
  let body = $state('');
  let maxBodyChars = $state(180);
  let sendState = $state<'idle' | 'sending' | 'sent' | 'error'>('idle');
  let error = $state('');
  let targetCache = $state<ConversationTarget[]>([]);
  let debugEvents = $state<DebugEvent[]>([]);
  let syncState = $state<'idle' | 'syncing' | 'synced' | 'error'>('idle');
  let syncMessage = $state('');
  let messageListEl: HTMLDivElement | undefined;
  let refreshTimer: ReturnType<typeof setInterval> | undefined;
  let initialNodeId = '';

  onMount(async () => {
    initialNodeId = new URLSearchParams(window.location.search).get('node') ?? '';
    await loadData();
    refreshTimer = setInterval(loadMessages, 3000);
  });

  onDestroy(() => {
    if (refreshTimer) clearInterval(refreshTimer);
  });

  async function loadMessages() {
    try {
      const [nextMessages, nextTargets] = await Promise.all([
        apiGet<any[]>('/messages'),
        apiGet<ConversationTarget[]>(targetsPath()).catch(() => [])
      ]);
      messages = nextMessages;
      mergeTargets(nextTargets);
      await loadDebugEvents();
      await scrollToLatestMessage();
    } catch (err) {
      error = err instanceof Error ? err.message : 'Messages could not be loaded.';
    }
  }

  async function loadData() {
    const [nextMessages, nextTargets] = await Promise.all([
      apiGet<any[]>('/messages'),
      apiGet<ConversationTarget[]>(targetsPath(Boolean(initialNodeId))).catch(() => []),
      apiGet<{ max_body_chars: number }>('/messages/limits')
        .then((limits) => {
          maxBodyChars = limits.max_body_chars;
        })
        .catch(() => null)
    ]);

    messages = nextMessages;
    mergeTargets(nextTargets);
    await loadDebugEvents();
    if (initialNodeId) {
      selectedTargetId = `node:${initialNodeId}`;
      initialNodeId = '';
    } else if (!selectedTargetId && targets.length > 0) {
      selectedTargetId = targets[0].id;
    }
    await scrollToLatestMessage();
  }

  function mergeTargets(nextTargets: ConversationTarget[]) {
    const byId = new Map(targetCache.map((target) => [target.id, target]));
    for (const target of nextTargets) {
      byId.set(target.id, target);
    }
    targetCache = Array.from(byId.values());
    targets = targetCache;
    if (selectedTargetId && !byId.has(selectedTargetId)) {
      selectedTargetId = targets[0]?.id ?? '';
    }
  }

  function targetsPath(includeEmpty = false) {
    return includeEmpty ? '/messages/targets?include_empty=true' : '/messages/targets';
  }


  async function loadDebugEvents() {
    debugEvents = await apiGet<DebugEvent[]>('/messages/debug?window_seconds=900&limit=25').catch(() => []);
  }

  async function syncMessages() {
    syncState = 'syncing';
    syncMessage = '';
    try {
      const result = await apiPost<{ status: string; events?: string[]; error?: string }>('/messages/sync', {});
      syncState = result.status === 'error' || result.status === 'timeout' ? 'error' : 'synced';
      syncMessage = result.error || `Sync returned ${result.events?.join(', ') || result.status}.`;
      await Promise.all([loadMessages(), loadDebugEvents()]);
    } catch (err) {
      syncState = 'error';
      syncMessage = err instanceof Error ? err.message : 'Message sync failed.';
    }
  }

  function debugTime(value: string) {
    return new Intl.DateTimeFormat('en', { timeStyle: 'medium' }).format(new Date(value));
  }

  function selectedTarget() {
    return targets.find((target) => target.id === selectedTargetId);
  }

  function selectedTargetWarning() {
    const target = selectedTarget();
    return target?.warning ?? null;
  }

  function visibleMessages() {
    const target = selectedTarget();
    if (!target) return [];
    const filtered =
      target.type === 'channel'
        ? messages.filter((message) => String(message.channel) === target.channel)
        : messages.filter((message) => {
            const rawDestination = message.raw_payload?.to_node_id;
            const rawSource = message.raw_payload?.pubkey_prefix || message.raw_payload?.public_key;
            const targetNodeId = target.id.replace('node:', '');
            return (
              message.from_node_id === targetNodeId ||
              message.to_node_id === targetNodeId ||
              rawDestination === target.toNodeId ||
              rawSource === target.toNodeId ||
              (typeof target.toNodeId === 'string' &&
                typeof rawSource === 'string' &&
                target.toNodeId.startsWith(rawSource))
            );
          });
    return filtered.sort((a, b) => messageTime(a) - messageTime(b));
  }

  function messageTime(message: any) {
    const value = message.received_at || message.sent_at || message.delivered_at;
    return value ? new Date(value).getTime() : 0;
  }

  function deliveryLabel(message: any) {
    const state = message.delivery_state || message.status;
    const labels: Record<string, string> = {
      acknowledged: 'Acknowledged',
      ack_timeout: 'ACK timeout',
      delivered: 'Delivered',
      failed: 'Failed',
      pending_ack: 'Pending ACK',
      queued: 'Queued',
      received: 'Received',
      sent: 'Sent',
      unknown: 'Unknown'
    };
    return labels[state] || state || 'Unknown';
  }

  async function scrollToLatestMessage() {
    await tick();
    if (!messageListEl) return;
    messageListEl.scrollTop = messageListEl.scrollHeight;
  }

  async function sendMessage() {
    const target = selectedTarget();
    if (!target) {
      error = 'Select a conversation first.';
      return;
    }
    if (target.warning && target.type === 'node') {
      error = target.warning;
      sendState = 'error';
      return;
    }
    if (body.length > maxBodyChars) {
      error = `Message is too long. Maximum is ${maxBodyChars} characters.`;
      sendState = 'error';
      return;
    }

    sendState = 'sending';
    error = '';
    try {
      await apiPost('/messages/send', {
        to_node_id: target.toNodeId,
        body,
        channel: target.channel,
        expect_ack: true
      });
      body = '';
      sendState = 'sent';
      await loadMessages();
    } catch (err) {
      sendState = 'error';
      error = err instanceof Error ? err.message : 'Message could not be sent.';
      await loadMessages();
    }
  }
</script>

<section class="page">
  <div class="page-header">
    <div>
      <h1>Messages</h1>
      <p class="muted">Conversations, delivery state, and real-time MeshCore messages.</p>
    </div>
  </div>

  <div class="messages-layout">
    <aside class="card conversation-list">
      <strong>Conversations</strong>
      {#if targets.length === 0}
        <p class="muted">No conversations yet. Start one from Nodes.</p>
      {:else}
        <div class="target-list">
          {#each targets as target}
            <button
              type="button"
              class:active={selectedTargetId === target.id}
              onclick={() => {
                selectedTargetId = target.id;
                sendState = 'idle';
                error = '';
                scrollToLatestMessage();
              }}
            >
              <span>{target.label}</span>
              <small>{target.warning ? `${target.detail} · Duplicate prefix` : target.detail}</small>
            </button>
          {/each}
        </div>
      {/if}
    </aside>

    <section class="card chat">
      <header class="chat-header">
        {#if selectedTarget()}
          <div>
            <strong>{selectedTarget()?.label}</strong>
            <span>{selectedTarget()?.detail}</span>
          </div>
        {:else}
          <strong>Select a conversation</strong>
        {/if}
      </header>
      {#if selectedTargetWarning()}
        <div class="warning-box">{selectedTargetWarning()}</div>
      {/if}
      <div class="message-list" bind:this={messageListEl}>
        {#if !selectedTarget()}
          <p class="muted">Choose a node or channel to start messaging.</p>
        {:else if visibleMessages().length === 0}
          <p class="muted">No message history is available for this conversation.</p>
        {:else}
          {#each visibleMessages() as message}
            <article class:outbound={message.direction === 'outbound'}>
              <span>{message.body}</span>
              <small>{deliveryLabel(message)}</small>
            </article>
          {/each}
        {/if}
      </div>

      <form onsubmit={(event) => { event.preventDefault(); sendMessage(); }}>
        <textarea bind:value={body} maxlength={maxBodyChars} placeholder="Message" required></textarea>
        <button disabled={sendState === 'sending' || !selectedTarget() || Boolean(selectedTargetWarning()) || body.length > maxBodyChars}>
          {sendState === 'sending' ? 'Sending...' : 'Send'}
        </button>
      </form>
      <div class="message-limit" class:over={body.length > maxBodyChars}>
        {body.length}/{maxBodyChars} characters
      </div>
      {#if sendState === 'sent'}<p class="muted">Message queued for delivery.</p>{/if}
      {#if error}<p class="error">{error}</p>{/if}
    </section>
  </div>

  <section class="card receive-debug">
    <div class="debug-header">
      <div>
        <h2>MeshCore Receive Debug</h2>
        <p class="muted">Official message events from the companion message queue.</p>
      </div>
      <button class="secondary" onclick={syncMessages} disabled={syncState === 'syncing'}>
        {syncState === 'syncing' ? 'Syncing...' : 'Sync messages'}
      </button>
    </div>
    {#if syncMessage}
      <p class:error={syncState === 'error'} class="muted">{syncMessage}</p>
    {/if}
    {#if debugEvents.length === 0}
      <p class="muted">No receive debug events are available yet.</p>
    {:else}
      <div class="debug-list">
        {#each debugEvents as event}
          <div class="debug-row">
            <span>{debugTime(event.created_at)}</span>
            <strong>{event.meshcore_event_type ?? event.type}</strong>
            <small>{event.severity}</small>
          </div>
        {/each}
      </div>
    {/if}
  </section>
</section>

<style>
  .messages-layout {
    display: grid;
    grid-template-columns: minmax(13rem, 18rem) 1fr;
    gap: 1rem;
  }

  .chat {
    display: grid;
    min-height: 34rem;
    max-height: calc(100vh - 11rem);
    grid-template-rows: auto 1fr auto;
    gap: 1rem;
  }

  .conversation-list {
    align-content: start;
  }

  .target-list {
    display: grid;
    gap: 0.5rem;
    margin-top: 0.9rem;
  }

  .target-list button {
    display: grid;
    gap: 0.2rem;
    width: 100%;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: var(--surface-soft);
    padding: 0.75rem;
    color: var(--text);
    text-align: left;
  }

  .target-list button.active {
    border-color: rgba(45, 212, 191, 0.46);
    background: var(--accent-soft);
  }

  .target-list span {
    overflow-wrap: anywhere;
    font-weight: 700;
  }

  .target-list small,
  .chat-header span {
    color: var(--muted);
  }

  .chat-header {
    border-bottom: 1px solid var(--border);
    padding-bottom: 0.8rem;
  }

  .chat-header div {
    display: grid;
    gap: 0.2rem;
  }

  .message-list {
    display: grid;
    align-content: start;
    gap: 0.75rem;
    min-height: 0;
    overflow-y: auto;
    padding-right: 0.2rem;
  }

  article {
    display: grid;
    max-width: 70%;
    gap: 0.25rem;
    border-radius: 8px;
    background: var(--surface-soft);
    padding: 0.75rem;
  }

  article.outbound {
    justify-self: end;
    background: rgba(45, 212, 191, 0.16);
  }

  form {
    display: grid;
    grid-template-columns: 1fr auto;
    gap: 0.75rem;
  }

  textarea {
    resize: vertical;
  }

  .message-limit {
    justify-self: end;
    color: var(--muted);
    font-size: 0.82rem;
    font-weight: 750;
  }

  .message-limit.over {
    color: #fecdd3;
  }

  .error {
    color: #fecdd3;
  }

  .warning-box {
    border: 1px solid rgba(245, 158, 11, 0.4);
    border-radius: 8px;
    background: rgba(245, 158, 11, 0.12);
    padding: 0.75rem;
    color: #fde68a;
    font-size: 0.86rem;
    font-weight: 750;
  }

  .receive-debug {
    margin-top: 1rem;
  }

  .debug-header {
    display: flex;
    align-items: start;
    justify-content: space-between;
    gap: 1rem;
    border-bottom: 1px solid var(--border);
    padding-bottom: 0.8rem;
  }

  .debug-header h2 {
    margin: 0;
    font-size: 1rem;
  }

  .debug-list {
    display: grid;
    gap: 0.45rem;
    margin-top: 0.8rem;
  }

  .debug-row {
    display: grid;
    grid-template-columns: 6rem minmax(0, 1fr) auto;
    gap: 0.75rem;
    align-items: center;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: var(--surface-soft);
    padding: 0.55rem 0.7rem;
  }

  .debug-row span,
  .debug-row small {
    color: var(--muted);
    font-size: 0.78rem;
  }

  .debug-row strong {
    overflow-wrap: anywhere;
  }

  @media (max-width: 820px) {
    .messages-layout,
    form,
    .debug-row {
      grid-template-columns: 1fr;
    }

    .debug-header {
      display: grid;
    }
  }
</style>
