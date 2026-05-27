export type ConnectionState =
  | 'disconnected'
  | 'connecting'
  | 'connected'
  | 'reconnecting'
  | 'error';

export type ConnectionStatus = {
  state: ConnectionState;
  connection_type: 'tcp';
  device_identifier: string | null;
  last_connected_at: string | null;
  last_disconnected_at: string | null;
  last_error: string | null;
  reconnect_attempt_count: number;
  api_library_version: string | null;
  firmware_version: string | null;
};

export type GatewayTelemetry = {
  battery_percentage?: string | number | null;
  battery_voltage_v?: string | number | null;
  ch1_voltage_v?: string | number | null;
  companion_prefix?: string | null;
  frequency_mhz?: string | number | null;
  bandwidth_khz?: string | number | null;
  spreading_factor?: number | null;
  tx_power_dbm?: string | number | null;
  node_count?: number | null;
  last_message_delivery?: string | null;
  node_status?: string | null;
  request_rate_limiter_tokens?: string | number | null;
  uptime_seconds?: number | null;
  last_rssi?: string | number | null;
  last_snr?: string | number | null;
  recorded_at?: string;
};

export type NodeSummary = {
  id: string;
  meshcore_id: string;
  public_key?: string | null;
  display_name: string | null;
  short_name: string | null;
  long_name?: string | null;
  is_favorite?: boolean;
  role?: string | null;
  status: string;
  battery_percentage: string | number | null;
  battery_voltage_v?: string | number | null;
  latitude?: string | number | null;
  longitude?: string | number | null;
  altitude?: string | number | null;
  uptime_seconds?: number | null;
  packets_received?: number | null;
  packets_sent?: number | null;
  packet_receive_errors?: number | null;
  rssi?: string | number | null;
  snr?: string | number | null;
  noise_floor?: string | number | null;
  last_heard_at: string | null;
  raw_info?: Record<string, any> | null;
  duplicate_public_key_prefix?: string | null;
  duplicate_nodes?: Array<{ id: string; display_name?: string | null; public_key?: string | null; meshcore_id?: string | null }>;
  suspect_stale_contact?: boolean;
  warning?: string | null;
};

export type DeviceSetting = {
  key: string;
  label: string;
  category: string;
  value: unknown;
  unit: string | null;
  editable: boolean;
  available: boolean;
  min_value: number | null;
  max_value: number | null;
  options?: Array<{ value: string; label: string; description?: string }>;
  description?: string | null;
};

export type ApiEvent = {
  id?: string;
  type: string;
  source?: string;
  severity?: string;
  payload: Record<string, unknown>;
  created_at: string;
};
