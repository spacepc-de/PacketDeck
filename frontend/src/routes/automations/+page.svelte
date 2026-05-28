<script lang="ts">
  import { onMount } from 'svelte';
  import { apiDelete, apiGet, apiPost, apiPut } from '$lib/api/client';
  import StatusPill from '$lib/components/StatusPill.svelte';

  type RuleForm = {
    id?: string;
    name: string;
    enabled: boolean;
    matchMode: 'contains' | 'regex';
    pattern: string;
    caseSensitive: boolean;
    sender: string;
    channel: string;
    actionType: 'mqtt.publish' | 'webhook.call' | 'meshcore.reply' | 'openai.chat_reply';
    mqttBrokerId: string;
    mqttTopic: string;
    mqttPayload: string;
    replyBody: string;
    webhookUrl: string;
    webhookPayload: string;
    allowPrivateWebhook: boolean;
    openaiModel: string;
    openaiSystemPrompt: string;
    openaiMaxOutputChars: number;
    openaiMode: 'command' | 'chatbot';
    openaiCommand: string;
    openaiIncludeContext: boolean;
    openaiAllowChannelReply: boolean;
    cooldownSeconds: number;
  };
  type Condition = Record<string, any>;
  type MqttBroker = { id: string; name: string; host: string; port: number; topic_prefix: string };

  const emptyForm: RuleForm = {
    name: '',
    enabled: true,
    matchMode: 'contains',
    pattern: '',
    caseSensitive: false,
    sender: '',
    channel: '',
    actionType: 'mqtt.publish',
    mqttBrokerId: '',
    mqttTopic: 'packetdeck/automations/message',
    mqttPayload: '{"body":"{{body}}","from":"{{from_meshcore_id}}","channel":"{{channel}}"}',
    replyBody: 'Command received.',
    webhookUrl: '',
    webhookPayload: '{"body":"{{body}}","from":"{{from_meshcore_id}}","channel":"{{channel}}"}',
    allowPrivateWebhook: false,
    openaiModel: 'gpt-4.1-mini',
    openaiSystemPrompt: 'You are PacketDeck, a concise radio messaging assistant. Reply briefly and use plain text only.',
    openaiMaxOutputChars: 180,
    openaiMode: 'command',
    openaiCommand: '!chat',
    openaiIncludeContext: true,
    openaiAllowChannelReply: false,
    cooldownSeconds: 30
  };

  let rules = $state<any[]>([]);
  let nodes = $state<any[]>([]);
  let brokers = $state<MqttBroker[]>([]);
  let form = $state<RuleForm>({ ...emptyForm });
  let maxMessageChars = $state(180);
  let runs = $state<any[]>([]);
  let selectedRuleId = $state('');
  let saveState = $state<'idle' | 'saving' | 'saved' | 'error'>('idle');
  let message = $state('');
  let loading = $state(true);
  const enabledCount = $derived(rules.filter((rule) => rule.enabled).length);
  const disabledCount = $derived(rules.length - enabledCount);
  const mqttCount = $derived(rules.filter((rule) => rule.actions?.[0]?.type === 'mqtt.publish').length);
  const chatbotCount = $derived(rules.filter((rule) => rule.actions?.[0]?.type === 'openai.chat_reply').length);
  const selectedRule = $derived(rules.find((rule) => rule.id === selectedRuleId));

  onMount(loadAll);

  async function loadAll() {
    loading = true;
    try {
      [rules, nodes, brokers] = await Promise.all([
        apiGet<any[]>('/automations'),
        apiGet<any[]>('/nodes').catch(() => []),
        apiGet<MqttBroker[]>('/mqtt/brokers').catch(() => [])
      ]);
      maxMessageChars = await apiGet<{ max_body_chars: number }>('/messages/limits')
        .then((limits) => limits.max_body_chars)
        .catch(() => 180);
    } finally {
      loading = false;
    }
  }

  function payloadFromForm() {
    const conditions = [];
    if (form.sender) conditions.push({ type: 'sender.equals', node_id: form.sender });
    if (form.channel) conditions.push({ type: 'channel.equals', channel: form.channel });
    if (form.actionType === 'openai.chat_reply' && form.openaiMode === 'command') {
      conditions.push({ type: 'message.regex', pattern: chatbotCommandPattern(), case_sensitive: false });
    } else if (form.matchMode === 'contains') {
      conditions.push({ type: 'message.contains', text: form.pattern, case_sensitive: form.caseSensitive });
    }

    const triggerType = form.actionType === 'openai.chat_reply' && form.openaiMode === 'chatbot' ? 'message.received' : 'message.matches';
    const triggerConfig =
      form.actionType === 'openai.chat_reply' && form.openaiMode === 'command'
        ? { pattern: chatbotCommandPattern(), case_sensitive: false }
        : form.matchMode === 'regex'
          ? { pattern: form.pattern, case_sensitive: form.caseSensitive }
          : { pattern: escapeRegex(form.pattern), case_sensitive: form.caseSensitive };

    const action = actionFromForm();

    return {
      name: form.name,
      enabled: form.enabled,
      trigger_type: triggerType,
      trigger_config: triggerConfig,
      conditions,
      actions: [action],
      cooldown_seconds: Number(form.cooldownSeconds) || 0
    };
  }

  function actionFromForm() {
    if (form.actionType === 'mqtt.publish') {
      return {
        type: 'mqtt.publish',
        broker_id: form.mqttBrokerId || null,
        topic: form.mqttTopic,
        payload: parseJsonOrText(form.mqttPayload),
        qos: 0,
        retain: false
      };
    }
    if (form.actionType === 'webhook.call') {
      return {
        type: 'webhook.call',
        url: form.webhookUrl,
        method: 'POST',
        payload: parseJsonOrText(form.webhookPayload),
        allow_private_network: form.allowPrivateWebhook
      };
    }
    if (form.actionType === 'openai.chat_reply') {
      return {
        type: 'openai.chat_reply',
        model: form.openaiModel,
        system_prompt: form.openaiSystemPrompt,
        max_output_chars: Math.min(Number(form.openaiMaxOutputChars) || maxMessageChars, maxMessageChars),
        chat_mode: form.openaiMode,
        command: form.openaiMode === 'command' ? form.openaiCommand : null,
        include_packetdeck_context: form.openaiIncludeContext,
        allow_channel_reply: form.openaiAllowChannelReply,
        expect_ack: true
      };
    }
    return {
      type: 'meshcore.reply',
      body: form.replyBody,
      expect_ack: true
    };
  }

  async function saveRule() {
    saveState = 'saving';
    message = '';
    try {
      const payload = payloadFromForm();
      if (form.id) {
        await apiPut(`/automations/${form.id}`, payload);
      } else {
        await apiPost('/automations', payload);
      }
      saveState = 'saved';
      message = 'Automation rule saved.';
      form = { ...emptyForm };
      selectedRuleId = '';
      await loadAll();
    } catch (err) {
      saveState = 'error';
      message = err instanceof Error ? err.message : 'Rule could not be saved.';
    }
  }

  async function editRule(rule: any) {
    selectedRuleId = rule.id;
    const conditionByType = new Map<string, Condition>((rule.conditions || []).map((condition: Condition) => [condition.type, condition]));
    const action = rule.actions?.[0] || {};
    form = {
      ...emptyForm,
      id: rule.id,
      name: rule.name,
      enabled: rule.enabled,
      matchMode: conditionByType.has('message.contains') ? 'contains' : 'regex',
      pattern: conditionByType.get('message.contains')?.text || rule.trigger_config?.pattern || '',
      caseSensitive: Boolean(rule.trigger_config?.case_sensitive),
      sender: conditionByType.get('sender.equals')?.node_id || '',
      channel: conditionByType.get('channel.equals')?.channel || '',
      actionType: action.type || 'mqtt.publish',
      mqttBrokerId: action.broker_id || '',
      mqttTopic: action.topic || emptyForm.mqttTopic,
      mqttPayload: stringifyPayload(action.payload, emptyForm.mqttPayload),
      replyBody: action.body || emptyForm.replyBody,
      webhookUrl: action.url || '',
      webhookPayload: stringifyPayload(action.payload, emptyForm.webhookPayload),
      allowPrivateWebhook: Boolean(action.allow_private_network),
      openaiModel: action.model || emptyForm.openaiModel,
      openaiSystemPrompt: action.system_prompt || emptyForm.openaiSystemPrompt,
      openaiMaxOutputChars: action.max_output_chars || emptyForm.openaiMaxOutputChars,
      openaiMode: action.chat_mode || (rule.trigger_type === 'message.received' ? 'chatbot' : emptyForm.openaiMode),
      openaiCommand: action.command || emptyForm.openaiCommand,
      openaiIncludeContext: action.include_packetdeck_context ?? emptyForm.openaiIncludeContext,
      openaiAllowChannelReply: action.allow_channel_reply ?? emptyForm.openaiAllowChannelReply,
      cooldownSeconds: rule.cooldown_seconds
    };
    runs = await apiGet<any[]>(`/automations/${rule.id}/runs`);
  }

  async function removeRule(rule: any) {
    await apiDelete(`/automations/${rule.id}`);
    if (selectedRuleId === rule.id) {
      selectedRuleId = '';
      form = { ...emptyForm };
      runs = [];
    }
    await loadAll();
  }

  async function toggleRule(rule: any) {
    await apiPost(`/automations/${rule.id}/${rule.enabled ? 'disable' : 'enable'}`);
    await loadAll();
  }

  async function testRule(rule: any) {
    saveState = 'saving';
    try {
      const run = await apiPost<any>(`/automations/${rule.id}/test`);
      saveState = run.status === 'completed' ? 'saved' : 'error';
      message = run.status === 'completed' ? 'Test run completed.' : run.error_message;
      runs = await apiGet<any[]>(`/automations/${rule.id}/runs`);
    } catch (err) {
      saveState = 'error';
      message = err instanceof Error ? err.message : 'Test run failed.';
    }
  }

  function parseJsonOrText(value: string) {
    try {
      return JSON.parse(value);
    } catch {
      return value;
    }
  }

  function stringifyPayload(value: unknown, fallback: string) {
    if (value === undefined || value === null) return fallback;
    return typeof value === 'string' ? value : JSON.stringify(value, null, 2);
  }

  function escapeRegex(value: string) {
    return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  }

  function chatbotCommandPattern() {
    const command = form.openaiCommand.trim() || '!chat';
    return `^\\s*${escapeRegex(command)}\\s+.+\\s*$`;
  }


  function resetForm() {
    form = { ...emptyForm };
    selectedRuleId = '';
    runs = [];
    message = '';
    saveState = 'idle';
  }

  function actionLabel(rule: any) {
    const type = rule.actions?.[0]?.type;
    if (type === 'mqtt.publish') return 'MQTT publish';
    if (type === 'webhook.call') return 'Webhook call';
    if (type === 'meshcore.reply') return 'MeshCore reply';
    if (type === 'openai.chat_reply') return 'OpenAI chatbot';
    return 'No action';
  }

  function triggerLabel(rule: any) {
    if (rule.trigger_type === 'message.received') return 'Every received message';
    const pattern = rule.trigger_config?.pattern;
    return pattern ? `Matches ${pattern}` : rule.trigger_type;
  }

  function ruleSummary(rule: any) {
    const conditions = rule.conditions || [];
    const sender = conditions.find((condition: Condition) => condition.type === 'sender.equals')?.node_id;
    const channel = conditions.find((condition: Condition) => condition.type === 'channel.equals')?.channel;
    const parts = [];
    if (sender) parts.push(`sender ${sender}`);
    if (channel) parts.push(`channel ${channel}`);
    if (rule.cooldown_seconds) parts.push(`${rule.cooldown_seconds}s cooldown`);
    return parts.length ? parts.join(' | ') : 'No sender or channel restrictions';
  }

  function formatRunStarted(value: string) {
    return value ? new Date(value).toLocaleString() : 'Unknown';
  }

  function ruleCanSave() {
    if (!form.name) return false;
    if (form.actionType === 'meshcore.reply' && form.replyBody.length > maxMessageChars) return false;
    if (form.actionType === 'openai.chat_reply') {
      if (form.openaiMode === 'command') return Boolean(form.openaiCommand.trim());
      return true;
    }
    return Boolean(form.pattern);
  }
</script>

<section class="page automations-page">
  <div class="automation-hero">
    <div class="hero-copy">
      <span class="eyebrow">Automation Center</span>
      <h1>Automations</h1>
      <p>Message-triggered MQTT publishes, webhooks, MeshCore replies, and OpenAI chatbot responses.</p>
    </div>
    <div class="hero-actions">
      <button class="secondary" onclick={loadAll} disabled={loading}>{loading ? 'Refreshing...' : 'Refresh'}</button>
      <button onclick={resetForm}>New Rule</button>
    </div>
  </div>

  <section class="automation-stats" aria-label="Automation overview">
    <div class="stat-tile">
      <span>Total</span>
      <strong>{rules.length}</strong>
    </div>
    <div class="stat-tile good">
      <span>Enabled</span>
      <strong>{enabledCount}</strong>
    </div>
    <div class="stat-tile muted-tile">
      <span>Disabled</span>
      <strong>{disabledCount}</strong>
    </div>
    <div class="stat-tile">
      <span>MQTT</span>
      <strong>{mqttCount}</strong>
    </div>
    <div class="stat-tile accent-tile">
      <span>Chatbots</span>
      <strong>{chatbotCount}</strong>
    </div>
  </section>

  <section class="automation-workspace">
    <form class="rule-builder" onsubmit={(event) => { event.preventDefault(); saveRule(); }}>
      <header class="panel-header">
        <div>
          <span class="eyebrow">{form.id ? 'Editing rule' : 'New rule'}</span>
          <h2>Rule Builder</h2>
        </div>
        {#if form.id}
          <button type="button" class="secondary" onclick={resetForm}>Clear</button>
        {/if}
      </header>

      <div class="builder-section">
        <h3>Trigger</h3>
        <div class="builder-grid">
          <label class="wide">
            <span>Name</span>
            <input bind:value={form.name} placeholder="Open garage via MeshCore" />
          </label>
          <label class="field-card sender-field">
            <span>Sender</span>
            <select bind:value={form.sender}>
              <option value="">Any node</option>
              {#each nodes as node}
                <option value={node.id}>{node.display_name || node.short_name || node.meshcore_id}</option>
                {#if node.meshcore_id}<option value={node.meshcore_id}>{node.meshcore_id}</option>{/if}
              {/each}
            </select>
          </label>
          <label class="field-card channel-field">
            <span>Channel</span>
            <input bind:value={form.channel} placeholder="Any channel" />
          </label>
          {#if form.actionType !== 'openai.chat_reply'}
            <label>
              <span>Match mode</span>
              <select bind:value={form.matchMode}>
                <option value="contains">Message contains</option>
                <option value="regex">Regex</option>
              </select>
            </label>
            <label>
              <span>Cooldown seconds</span>
              <input type="number" min="0" bind:value={form.cooldownSeconds} />
            </label>
            <label class="wide">
              <span>Message pattern</span>
              <input bind:value={form.pattern} placeholder="garage open" />
            </label>
          {:else}
            <label>
              <span>Cooldown seconds</span>
              <input type="number" min="0" bind:value={form.cooldownSeconds} />
            </label>
            <div class="notice wide">OpenAI rules use command or chatbot matching.</div>
          {/if}
          <label class="toggle">
            <input type="checkbox" bind:checked={form.caseSensitive} />
            <span>Case sensitive</span>
          </label>
          <label class="toggle">
            <input type="checkbox" bind:checked={form.enabled} />
            <span>Enabled</span>
          </label>
        </div>
      </div>

      <div class="builder-section action-section">
        <h3>Action</h3>
        <div class="builder-grid">
          <label class="wide">
            <span>Action type</span>
            <select bind:value={form.actionType}>
              <option value="mqtt.publish">MQTT publish</option>
              <option value="webhook.call">Webhook call</option>
              <option value="meshcore.reply">MeshCore reply</option>
              <option value="openai.chat_reply">OpenAI chatbot reply</option>
            </select>
          </label>
          {#if form.actionType === 'mqtt.publish'}
            <label class="wide">
              <span>MQTT server</span>
              <select bind:value={form.mqttBrokerId}>
                <option value="">Latest configured server</option>
                {#each brokers as broker}
                  <option value={broker.id}>{broker.name} - {broker.host}:{broker.port}</option>
                {/each}
              </select>
            </label>
            <label class="wide">
              <span>MQTT topic</span>
              <input bind:value={form.mqttTopic} />
            </label>
            <label class="wide">
              <span>MQTT payload</span>
              <textarea bind:value={form.mqttPayload}></textarea>
            </label>
          {:else if form.actionType === 'webhook.call'}
            <label class="wide">
              <span>Webhook URL</span>
              <input bind:value={form.webhookUrl} placeholder="https://example.com/hook" />
            </label>
            <label class="wide">
              <span>Webhook JSON payload</span>
              <textarea bind:value={form.webhookPayload}></textarea>
            </label>
            <label class="toggle wide">
              <input type="checkbox" bind:checked={form.allowPrivateWebhook} />
              <span>Allow private network target</span>
            </label>
          {:else if form.actionType === 'openai.chat_reply'}
            <label>
              <span>Chat mode</span>
              <select bind:value={form.openaiMode}>
                <option value="command">Command prefix</option>
                <option value="chatbot">Chatbot mode</option>
              </select>
            </label>
            {#if form.openaiMode === 'command'}
              <label>
                <span>Command prefix</span>
                <input bind:value={form.openaiCommand} placeholder="!chat" />
              </label>
            {:else}
              <div class="notice wide">Chatbot mode listens broadly and yields to other matching automations.</div>
            {/if}
            <label>
              <span>Model</span>
              <input bind:value={form.openaiModel} placeholder="gpt-4.1-mini" />
            </label>
            <label>
              <span>Max reply characters</span>
              <input type="number" min="1" max={maxMessageChars} bind:value={form.openaiMaxOutputChars} />
            </label>
            <label class="toggle wide">
              <input type="checkbox" bind:checked={form.openaiIncludeContext} />
              <span>Include PacketDeck context</span>
            </label>
            <label class="toggle wide">
              <input type="checkbox" bind:checked={form.openaiAllowChannelReply} />
              <span>Reply in public channels</span>
            </label>
            <label class="wide">
              <span>System prompt</span>
              <textarea bind:value={form.openaiSystemPrompt}></textarea>
            </label>
          {:else}
            <label class="wide">
              <span>Reply text</span>
              <textarea maxlength={maxMessageChars} bind:value={form.replyBody}></textarea>
              <small>{form.replyBody.length}/{maxMessageChars} characters</small>
            </label>
          {/if}
        </div>
      </div>

      <footer class="form-actions">
        <button type="submit" disabled={saveState === 'saving' || !ruleCanSave()}>
          {saveState === 'saving' ? 'Saving...' : form.id ? 'Update Rule' : 'Create Rule'}
        </button>
        {#if message}<p class:error={saveState === 'error'}>{message}</p>{/if}
      </footer>
    </form>

    <aside class="rules-panel">
      <header class="panel-header">
        <div>
          <span class="eyebrow">Rules</span>
          <h2>Active Set</h2>
        </div>
      </header>

      {#if loading}
        <div class="empty-state">Loading rules...</div>
      {:else if rules.length === 0}
        <div class="empty-state">No automation rules yet.</div>
      {:else}
        <div class="rule-list">
          {#each rules as rule}
            <article class:active={selectedRuleId === rule.id} class="rule-card">
              <header>
                <div>
                  <h3>{rule.name}</h3>
                  <p>{ruleSummary(rule)}</p>
                </div>
                <StatusPill status={rule.enabled ? 'enabled' : 'disabled'} />
              </header>
              <div class="rule-meta">
                <span>{triggerLabel(rule)}</span>
                <span>{actionLabel(rule)}</span>
              </div>
              <footer class="row-actions">
                <button class="secondary" onclick={() => editRule(rule)}>Edit</button>
                <button class="secondary" onclick={() => toggleRule(rule)}>{rule.enabled ? 'Disable' : 'Enable'}</button>
                <button class="secondary" onclick={() => testRule(rule)}>Test</button>
                <button class="secondary danger-button" onclick={() => removeRule(rule)}>Delete</button>
              </footer>
            </article>
          {/each}
        </div>
      {/if}
    </aside>
  </section>

  {#if runs.length > 0}
    <section class="runs-panel">
      <header class="panel-header">
        <div>
          <span class="eyebrow">Run History</span>
          <h2>{selectedRule?.name ?? 'Selected rule'}</h2>
        </div>
      </header>
      <div class="run-list">
        {#each runs as run}
          <article class="run-row">
            <div>
              <strong>{formatRunStarted(run.started_at)}</strong>
              {#if run.error_message}<p>{run.error_message}</p>{/if}
            </div>
            <StatusPill status={run.status} />
          </article>
        {/each}
      </div>
    </section>
  {/if}
</section>

<style>
  .automations-page {
    max-width: 1480px;
    display: grid;
    gap: 1rem;
  }

  .automation-hero,
  .rule-builder,
  .rules-panel,
  .runs-panel {
    border: 1px solid var(--border);
    border-radius: 8px;
    background: rgba(15, 23, 42, 0.72);
    box-shadow: var(--shadow);
  }

  .automation-hero {
    display: flex;
    justify-content: space-between;
    gap: 1rem;
    align-items: flex-end;
    padding: 1.25rem;
  }

  .hero-copy {
    display: grid;
    gap: 0.35rem;
  }

  .hero-copy h1,
  .panel-header h2,
  .builder-section h3,
  .rule-card h3 {
    margin: 0;
  }

  .hero-copy p,
  .rule-card p,
  .run-row p {
    margin: 0;
    color: var(--muted);
  }

  .hero-actions,
  .panel-header,
  .form-actions,
  .row-actions {
    display: flex;
    align-items: center;
    gap: 0.65rem;
  }

  .automation-stats {
    display: grid;
    grid-template-columns: repeat(5, minmax(0, 1fr));
    gap: 0.75rem;
  }

  .stat-tile {
    border: 1px solid var(--border);
    border-radius: 8px;
    background: rgba(15, 23, 42, 0.55);
    padding: 0.95rem;
    display: grid;
    gap: 0.35rem;
    min-width: 0;
  }

  .stat-tile span,
  .eyebrow {
    color: var(--muted);
    font-size: 0.76rem;
    font-weight: 800;
    letter-spacing: 0;
    text-transform: uppercase;
  }

  .stat-tile strong {
    font-size: 1.65rem;
    line-height: 1;
  }

  .stat-tile.good {
    border-color: rgba(34, 197, 94, 0.35);
  }

  .stat-tile.muted-tile {
    border-color: rgba(148, 163, 184, 0.25);
  }

  .stat-tile.accent-tile {
    border-color: rgba(96, 165, 250, 0.35);
  }

  .automation-workspace {
    display: grid;
    grid-template-columns: minmax(0, 1.15fr) minmax(360px, 0.85fr);
    gap: 1rem;
    align-items: start;
  }

  .rule-builder,
  .rules-panel,
  .runs-panel {
    padding: 1rem;
  }

  .panel-header {
    justify-content: space-between;
    margin-bottom: 1rem;
  }

  .builder-section {
    display: grid;
    gap: 0.8rem;
    padding: 1rem 0;
    border-top: 1px solid var(--border);
  }

  .builder-section:first-of-type {
    border-top: 0;
    padding-top: 0;
  }

  .builder-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 0.75rem;
  }

  label {
    display: grid;
    gap: 0.35rem;
    color: var(--muted);
    font-weight: 700;
    min-width: 0;
  }

  label input,
  label select,
  label textarea {
    width: 100%;
    max-width: 100%;
    min-width: 0;
    box-sizing: border-box;
  }

  .field-card {
    border: 1px solid rgba(148, 163, 184, 0.18);
    border-radius: 8px;
    background: rgba(2, 6, 23, 0.18);
    padding: 0.7rem;
  }

  label span,
  small {
    font-size: 0.82rem;
  }

  .wide {
    grid-column: 1 / -1;
  }

  textarea {
    min-height: 8rem;
    resize: vertical;
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  }

  .toggle {
    display: flex;
    align-items: center;
    gap: 0.55rem;
    min-height: 2.75rem;
  }

  .toggle input {
    min-height: auto;
    width: auto;
  }

  .notice {
    border: 1px solid rgba(96, 165, 250, 0.28);
    border-radius: 8px;
    background: rgba(30, 64, 175, 0.14);
    color: #bfdbfe;
    padding: 0.75rem 0.85rem;
    font-size: 0.88rem;
    line-height: 1.45;
  }

  .form-actions {
    justify-content: space-between;
    flex-wrap: wrap;
    padding-top: 1rem;
    border-top: 1px solid var(--border);
  }

  .form-actions p {
    margin: 0;
    color: var(--muted);
  }

  .form-actions .error {
    color: #fecdd3;
  }

  .rule-list,
  .run-list {
    display: grid;
    gap: 0.75rem;
  }

  .rule-card,
  .run-row,
  .empty-state {
    border: 1px solid var(--border);
    border-radius: 8px;
    background: rgba(15, 23, 42, 0.45);
    padding: 0.9rem;
  }

  .rule-card {
    display: grid;
    gap: 0.8rem;
  }

  .rule-card.active {
    border-color: var(--accent);
    background: var(--accent-soft);
  }

  .rule-card header,
  .run-row {
    display: flex;
    justify-content: space-between;
    gap: 0.75rem;
    align-items: flex-start;
  }

  .rule-meta {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 0.5rem;
  }

  .rule-meta span {
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 0.5rem 0.6rem;
    color: var(--text);
    background: rgba(2, 6, 23, 0.28);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .row-actions {
    flex-wrap: wrap;
  }

  .row-actions button {
    min-height: 2rem;
    padding: 0.35rem 0.55rem;
    font-size: 0.8rem;
  }

  .danger-button {
    color: #fecdd3;
  }

  .empty-state {
    color: var(--muted);
    text-align: center;
  }

  @media (max-width: 1180px) {
    .automation-workspace {
      grid-template-columns: 1fr;
    }
  }

  @media (max-width: 900px) {
    .sender-field,
    .channel-field {
      grid-column: 1 / -1;
    }
  }

  @media (max-width: 760px) {
    .automation-hero,
    .hero-actions,
    .panel-header,
    .form-actions,
    .rule-card header,
    .run-row {
      align-items: stretch;
      flex-direction: column;
    }

    .hero-actions button,
    .form-actions button {
      width: 100%;
    }

    .automation-stats,
    .builder-grid,
    .rule-meta {
      grid-template-columns: 1fr;
    }

    .rule-builder,
    .rules-panel,
    .runs-panel,
    .automation-hero {
      padding: 0.85rem;
    }
  }
</style>

