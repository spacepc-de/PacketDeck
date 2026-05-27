import { env } from '$env/dynamic/public';
import { writable } from 'svelte/store';
import type { ApiEvent } from '$lib/types/api';

export const latestEvent = writable<ApiEvent | null>(null);
export const eventConnectionState = writable<'idle' | 'connected' | 'error'>('idle');

export function connectEventStream() {
  const url = env.PUBLIC_WS_URL || 'ws://localhost:8000/api/v1/ws/events';
  const socket = new WebSocket(url);
  socket.onopen = () => eventConnectionState.set('connected');
  socket.onerror = () => eventConnectionState.set('error');
  socket.onclose = () => eventConnectionState.set('idle');
  socket.onmessage = (message) => {
    latestEvent.set(JSON.parse(message.data) as ApiEvent);
  };
  return () => socket.close();
}
