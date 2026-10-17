export class ApiError extends Error {
  constructor(status, data) {
    const detail = data?.detail ?? data?.message ?? data?.error_code;
    super(typeof detail === 'string' ? detail : (detail ? JSON.stringify(detail) : `请求失败 (${status})`));
    this.status = status; this.data = data; this.detail = detail;
  }
}

// Mutations and paid calls are intentionally never retried.
export async function api(path, {method = 'GET', body, rawBody, signal, ...options} = {}) {
  const headers = {'Accept': 'application/json', ...options.headers};
  if (body !== undefined || rawBody !== undefined) headers['Content-Type'] = 'application/json';
  const response = await fetch(path, {...options, method, headers, signal,
    body: rawBody !== undefined ? rawBody : body !== undefined ? JSON.stringify(body) : undefined});
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(response.status, data);
  return data;
}
