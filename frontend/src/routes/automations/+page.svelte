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

  onMount(loadAll);

  async function loadAll() {
    [rules, nodes, brokers] = await Promise.all([
      apiGet<any[]>('/automations'),
      apiGet<any[]>('/nodes').catch(() => []),
      apiGet<MqttBroker[]>('/mqtt/brokers').catch(() => [])
    ]);
    maxMessageChars = await apiGet<{ max_body_chars: number }>('/messages/limits')
      .then((limits) => limits.max_body_chars)
      .catch(() => 180);
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
  <div class="page-header">
    <div>
      <h1>Automations</h1>
      <p class="muted">Run MQTT publishes, webhooks, MeshCore replies, or OpenAI chatbot responses when selected messages arrive.</p>
    </div>
    <button onclick={() => { form = { ...emptyForm }; selectedRuleId = ''; runs = []; }}>New Rule</button>
  </div>

  <section class="builder">
    <div class="card">
      <h2>Rule Builder</h2>
      <div class="builder-grid">
        <label>
          <span>Name</span>
          <input bind:value={form.name} placeholder="Open garage via MeshCore" />
        </label>
        <label>
          <span>Sender</span>
          <select bind:value={form.sender}>
            <option value="">Any node</option>
            {#each nodes as node}
              <option value={node.id}>{node.display_name || node.short_name || node.meshcore_id}</option>
              {#if node.meshcore_id}<option value={node.meshcore_id}>{node.meshcore_id}</option>{/if}
            {/each}
          </select>
        </label>
        <label>
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
          <label class="wide">
            <span>Message pattern</span>
            <input bind:value={form.pattern} placeholder="garage open" />
          </label>
        {:else}
          <div class="info-box wide">
            OpenAI chatbot rules use their own match behavior. Command prefix mode only reacts to its command, while chatbot mode listens broadly and yields to other matching automations.
          </div>
        {/if}
        <label>
          <span>Cooldown seconds</span>
          <input type="number" min="0" bind:value={form.cooldownSeconds} />
        </label>
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

    <div class="card">
      <h2>Action</h2>
      <div class="builder-grid">
        <label>
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
            <span>Allow private network webhook target</span>
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
            <p class="info-box wide">
              Command prefix mode only sends messages starting with {form.openaiCommand || '!chat'} to OpenAI. Only the text after the command is used as the chatbot prompt.
            </p>
          {:else}
            <p class="info-box wide">
              Chatbot mode sends normal incoming messages directly to OpenAI. Messages that match another automation or command are ignored by the chatbot rule.
            </p>
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
            <span>Include PacketDeck gateway, node, telemetry, and recent message context</span>
          </label>
          <label class="toggle wide">
            <input type="checkbox" bind:checked={form.openaiAllowChannelReply} />
            <span>Reply in public channels</span>
          </label>
          <label class="wide">
            <span>System prompt</span>
            <textarea bind:value={form.openaiSystemPrompt}></textarea>
          </label>
          <p class="muted wide">Uses the backend OPENAI_API_KEY environment variable. Replies are capped at {maxMessageChars} characters. PacketDeck context lets the chatbot answer questions about known nodes, last heard times, battery, gateway state, telemetry, and recent messages.</p>
        {:else}
          <label class="wide">
            <span>Reply text</span>
            <textarea maxlength={maxMessageChars} bind:value={form.replyBody}></textarea>
            <small>{form.replyBody.length}/{maxMessageChars} characters</small>
          </label>
        {/if}
      </div>
      <div class="form-actions">
        <button
          onclick={saveRule}
          disabled={saveState === 'saving' || !ruleCanSave()}
        >
          {saveState === 'saving' ? 'Saving...' : form.id ? 'Update Rule' : 'Create Rule'}
        </button>
        {#if message}<p class:error={saveState === 'error'} class="muted">{message}</p>{/if}
      </div>
    </div>
  </section>

  {#if rules.length === 0}
    <div class="card">No automation rules have been created yet.</div>
  {:else}
    <table>
      <thead><tr><th>Name</th><th>Trigger</th><th>Action</th><th>Status</th><th>Cooldown</th><th>Actions</th></tr></thead>
      <tbody>
        {#each rules as rule}
          <tr class:active={selectedRuleId === rule.id}>
            <td>{rule.name}</td>
            <td>{rule.trigger_type}</td>
            <td>{rule.actions?.[0]?.type ?? 'None'}</td>
            <td><StatusPill status={rule.enabled ? 'enabled' : 'disabled'} /></td>
            <td>{rule.cooldown_seconds}s</td>
            <td class="row-actions">
              <button class="secondary" onclick={() => editRule(rule)}>Edit</button>
              <button class="secondary" onclick={() => toggleRule(rule)}>{rule.enabled ? 'Disable' : 'Enable'}</button>
              <button class="secondary" onclick={() => testRule(rule)}>Test</button>
              <button class="secondary" onclick={() => removeRule(rule)}>Delete</button>
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
  {/if}

  {#if runs.length > 0}
    <section class="card">
      <h2>Run History</h2>
      <table>
        <thead><tr><th>Started</th><th>Status</th><th>Error</th></tr></thead>
        <tbody>
          {#each runs as run}
            <tr>
              <td>{new Date(run.started_at).toLocaleString()}</td>
              <td><StatusPill status={run.status} /></td>
              <td>{run.error_message ?? ''}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </section>
  {/if}
</section>

<style>
  h2 {
    margin: 0 0 1rem;
  }

  .automations-page {
    max-width: 1480px;
  }

  .builder {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    gap: 1rem;
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
  }

  .toggle input {
    min-height: auto;
  }

  .info-box {
    border: 1px solid rgba(96, 165, 250, 0.25);
    border-radius: 8px;
    background: rgba(30, 64, 175, 0.18);
    color: #bfdbfe;
    padding: 0.8rem 0.9rem;
    font-size: 0.9rem;
    line-height: 1.45;
  }

  .form-actions {
    display: flex;
    align-items: center;
    gap: 1rem;
    margin-top: 1rem;
  }

  .row-actions {
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem;
  }

  .row-actions button {
    min-height: 2rem;
    padding: 0.35rem 0.55rem;
    font-size: 0.8rem;
  }

  tr.active {
    background: var(--accent-soft);
  }

  .error {
    color: #fecdd3;
  }

  @media (max-width: 980px) {
    .builder,
    .builder-grid {
      grid-template-columns: 1fr;
    }
  }
</style>
