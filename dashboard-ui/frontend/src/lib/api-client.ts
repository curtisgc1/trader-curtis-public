const BASE_URL = '';

export async function fetchApi<T>(path: string, fallback: T): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`);
  if (!res.ok) {
    if (res.status === 404) return fallback;
    throw new Error(`API ${path}: ${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

export async function postApi<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`POST ${path}: ${res.status} ${text}`);
  }
  return res.json() as Promise<T>;
}
