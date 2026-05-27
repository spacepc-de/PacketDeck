import { env } from '$env/dynamic/public';

const apiBase = env.PUBLIC_API_BASE_URL || 'http://localhost:8000/api/v1';

export async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(`${apiBase}${path}`);
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json() as Promise<T>;
}

export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`${apiBase}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body)
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json() as Promise<T>;
}

export async function apiPatch<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${apiBase}${path}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json() as Promise<T>;
}

export async function apiPut<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${apiBase}${path}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json() as Promise<T>;
}

export async function apiDelete(path: string): Promise<void> {
  const response = await fetch(`${apiBase}${path}`, { method: 'DELETE' });
  if (!response.ok) {
    throw new Error(await response.text());
  }
}
