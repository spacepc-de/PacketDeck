<script lang="ts">
  import { onMount } from 'svelte';
  import { apiDelete, apiGet, apiPost, apiPut } from '$lib/api/client';
  import StatusPill from '$lib/components/StatusPill.svelte';

  type MqttBroker = {
    id: string;
    name: string;
    host: string;
    port: number;
    username: string | null;
    has_password: boolean;
    tls_enabled: boolean;
    client_id: string | null;
    topic_prefix: string;
    retain_settings: Record<string, unknown>;
    created_at: string;
    updated_at: string;
  };

  type BrokerForm = {
    name: string;
    host: string;
    port: number;
    username: string;
    password: string;
    tls_enabled: boolean;
    client_id: string;
    topic_prefix: string;
  };

  const emptyForm: BrokerForm = {
    name: '',
    host: '',
    port: 1883,
    username: '',
    password: '',
    tls_enabled: false,
    client_id: '',
    topic_prefix: 'packetdeck'
  };

  let status = $state<{ connected: boolean; last_error: string | null } | null>(null);
  let brokers = $state<MqttBroker[]>([]);
  let form = $state<BrokerForm>({ ...emptyForm });
  let editingId = $state<string | null>(null);
  let loading = $state(true);
  let saving = $state(false);
  let testingId = $state<string | null>(null);
  let error = $state('');
  let notice = $state('');

  onMount(loadMqtt);

  async function loadMqtt() {
    loading = true;
    error = '';
    try {
      [status, brokers] = await Promise.all([
        apiGet<{ connected: boolean; last_error: string | null }>('/mqtt/status'),
        apiGet<MqttBroker[]>('/mqtt/brokers')
      ]);
    } catch (err) {
      error = err instanceof Error ? err.message : 'MQTT settings could not be loaded.';
    } finally {
      loading = false;
    }
  }

  function editBroker(broker: MqttBroker) {
    editingId = broker.id;
    form = {
      name: broker.name,
      host: broker.host,
      port: broker.port,
      username: broker.username ?? '',
      password: '',
      tls_enabled: broker.tls_enabled,
      client_id: broker.client_id ?? '',
      topic_prefix: broker.topic_prefix
    };
    notice = broker.has_password ? 'Password is configured. Leave password empty to keep it unchanged.' : '';
  }

  function resetForm() {
    editingId = null;
    form = { ...emptyForm };
    notice = '';
  }

  function brokerPayload() {
    return {
      name: form.name.trim(),
      host: form.host.trim(),
      port: Number(form.port),
      username: form.username.trim() || null,
      password: form.password || null,
      tls_enabled: form.tls_enabled,
      client_id: form.client_id.trim() || null,
      topic_prefix: form.topic_prefix.trim() || 'packetdeck',
      retain_settings: {}
    };
  }

  async function saveBroker() {
    error = '';
    notice = '';
    saving = true;
    try {
      const payload = brokerPayload();
      if (!payload.name || !payload.host) throw new Error('Name and host are required.');
      if (editingId) {
        await apiPut<MqttBroker>(`/mqtt/brokers/${editingId}`, payload);
        notice = 'MQTT broker updated.';
      } else {
        await apiPost<MqttBroker>('/mqtt/brokers', payload);
        notice = 'MQTT broker added.';
      }
      resetForm();
      await loadMqtt();
    } catch (err) {
      error = err instanceof Error ? err.message : 'MQTT broker could not be saved.';
    } finally {
      saving = false;
    }
  }

  async function deleteBroker(id: string) {
    error = '';
    notice = '';
    try {
      await apiDelete(`/mqtt/brokers/${id}`);
      if (editingId === id) resetForm();
      notice = 'MQTT broker removed.';
      await loadMqtt();
    } catch (err) {
      error = err instanceof Error ? err.message : 'MQTT broker could not be removed.';
    }
  }

  async function testBroker(id: string) {
    error = '';
    notice = '';
    testingId = id;
    try {
      await apiPost('/mqtt/test', {
        broker_id: id,
        topic: `${brokers.find((broker) => broker.id === id)?.topic_prefix ?? 'packetdeck'}/test`,
        payload: { message: 'PacketDeck test publish' }
      });
      notice = 'Test publish succeeded.';
    } catch (err) {
      error = err instanceof Error ? err.message : 'MQTT test publish failed.';
    } finally {
      testingId = null;
    }
  }
</script>

<section class="page mqtt-page">
  <div class="page-header">
    <div>
      <h1>MQTT</h1>
      <p class="muted">Configure multiple brokers with credentials, TLS, topic prefixes, and test publishes.</p>
    </div>
    {#if status}<StatusPill status={status.connected ? 'connected' : 'configured'} />{/if}
  </div>

  {#if error}<div class="card error">{error}</div>{/if}
  {#if notice}<div class="card">{notice}</div>{/if}

  <section class="card">
    <div class="section-header">
      <h2>{editingId ? 'Edit MQTT Server' : 'Add MQTT Server'}</h2>
      {#if editingId}<button class="secondary" onclick={resetForm}>Cancel edit</button>{/if}
    </div>
    <div class="broker-grid">
      <label>
        <span>Name</span>
        <input bind:value={form.name} placeholder="Home Assistant" />
      </label>
      <label>
        <span>Host</span>
        <input bind:value={form.host} placeholder="mqtt.local" />
      </label>
      <label>
        <span>Port</span>
        <input type="number" min="1" max="65535" bind:value={form.port} />
      </label>
      <label>
        <span>Topic prefix</span>
        <input bind:value={form.topic_prefix} placeholder="packetdeck" />
      </label>
      <label>
        <span>Username</span>
        <input autocomplete="username" bind:value={form.username} placeholder="Optional" />
      </label>
      <label>
        <span>Password</span>
        <input autocomplete="current-password" type="password" bind:value={form.password} placeholder="Optional" />
      </label>
      <label>
        <span>Client ID</span>
        <input bind:value={form.client_id} placeholder="Optional" />
      </label>
      <label class="toggle">
        <input type="checkbox" bind:checked={form.tls_enabled} />
        <span>Use TLS</span>
      </label>
    </div>
    <div class="form-actions">
      <button disabled={saving} onclick={saveBroker}>{saving ? 'Saving...' : editingId ? 'Save Server' : 'Add Server'}</button>
    </div>
  </section>

  {#if loading}
    <div class="card">Loading MQTT servers...</div>
  {:else if brokers.length === 0}
    <div class="card">No MQTT servers are configured.</div>
  {:else}
    <section class="broker-list">
      {#each brokers as broker}
        <article class="card broker-card">
          <header>
            <div>
              <h2>{broker.name}</h2>
              <p class="muted">{broker.host}:{broker.port}</p>
            </div>
            <StatusPill status={broker.tls_enabled ? 'tls' : 'tcp'} />
          </header>
          <div class="broker-meta">
            <div><span>Username</span><strong>{broker.username ?? 'None'}</strong></div>
            <div><span>Password</span><strong>{broker.has_password ? 'Configured' : 'None'}</strong></div>
            <div><span>Client ID</span><strong>{broker.client_id ?? 'Auto'}</strong></div>
            <div><span>Topic prefix</span><strong>{broker.topic_prefix}</strong></div>
          </div>
          <div class="broker-actions">
            <button class="secondary" onclick={() => editBroker(broker)}>Edit</button>
            <button class="secondary" disabled={testingId === broker.id} onclick={() => testBroker(broker.id)}>
              {testingId === broker.id ? 'Testing...' : 'Test Publish'}
            </button>
            <button class="secondary danger" onclick={() => deleteBroker(broker.id)}>Delete</button>
          </div>
        </article>
      {/each}
    </section>
  {/if}
</section>

<style>
  .mqtt-page {
    max-width: 1480px;
  }

  h2 {
    margin: 0;
    font-size: 1.08rem;
  }

  .section-header,
  .broker-card header,
  .broker-actions,
  .form-actions {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.75rem;
  }

  .broker-grid {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 0.85rem;
    margin-top: 1rem;
  }

  label {
    display: grid;
    gap: 0.4rem;
    color: var(--muted);
    font-weight: 750;
  }

  .toggle {
    align-content: end;
    grid-template-columns: auto 1fr;
    align-items: center;
    min-height: 4.4rem;
  }

  .toggle input {
    min-height: auto;
  }

  .form-actions {
    justify-content: end;
    margin-top: 1rem;
  }

  .broker-list {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(22rem, 1fr));
    gap: 1rem;
  }

  .broker-card {
    display: grid;
    gap: 1rem;
  }

  .broker-card p {
    margin: 0.25rem 0 0;
  }

  .broker-meta {
    display: grid;
    gap: 0.65rem;
  }

  .broker-meta div {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    border-top: 1px solid var(--border);
    padding-top: 0.65rem;
  }

  .broker-meta div:first-child {
    border-top: 0;
    padding-top: 0;
  }

  .broker-meta span {
    color: var(--muted);
    font-weight: 750;
  }

  .broker-meta strong {
    text-align: right;
    overflow-wrap: anywhere;
  }

  .broker-actions {
    justify-content: end;
    flex-wrap: wrap;
  }

  button.danger {
    border-color: rgba(251, 113, 133, 0.38);
    color: #fecdd3;
  }

  .error {
    color: #fecdd3;
  }

  @media (max-width: 980px) {
    .broker-grid {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
  }

  @media (max-width: 640px) {
    .broker-grid,
    .broker-list {
      grid-template-columns: 1fr;
    }
  }
</style>
