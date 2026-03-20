/**
 * Fetch wrapper that auto-injects the Bearer token from the auth store.
 *
 * Usage:
 *   import { api } from './api'
 *   const data = await api.get('/api/projects')
 *   const result = await api.post('/api/projects', { name: 'My Project' })
 */

// In-memory token store — the token is NEVER written to localStorage.
let _accessToken = null

export function setToken(token) {
  _accessToken = token
}

export function clearToken() {
  _accessToken = null
}

export function getToken() {
  return _accessToken
}

// ─── Core fetch wrapper ────────────────────────────────────────────────────────

async function request(method, url, body, options = {}) {
  const headers = {
    'Content-Type': 'application/json',
    ...options.headers,
  }

  if (_accessToken) {
    headers['Authorization'] = `Bearer ${_accessToken}`
  }

  const config = {
    method,
    headers,
    ...options,
  }

  if (body !== undefined) {
    config.body = JSON.stringify(body)
  }

  const response = await fetch(url, config)

  // Handle 401 — token expired or revoked; trigger re-login via custom event
  if (response.status === 401) {
    const data = await response.json().catch(() => ({}))
    const code = data?.detail?.code ?? 'UNAUTHORIZED'

    // Notify auth context to clear session
    window.dispatchEvent(new CustomEvent('auth:unauthorized', { detail: { code } }))

    const error = new Error(data?.detail?.message ?? 'Unauthorized')
    error.status = 401
    error.code = code
    throw error
  }

  // For non-JSON responses (e.g. 204 No Content)
  if (response.status === 204) {
    return null
  }

  const data = await response.json()

  if (!response.ok) {
    const message =
      data?.detail?.message ??
      (typeof data?.detail === 'string' ? data.detail : null) ??
      `Request failed with status ${response.status}`

    const error = new Error(message)
    error.status = response.status
    error.code = data?.detail?.code ?? null
    error.data = data
    throw error
  }

  return data
}

// ─── HTTP method helpers ───────────────────────────────────────────────────────

export const api = {
  get:    (url, options)        => request('GET',    url, undefined, options),
  post:   (url, body, options)  => request('POST',   url, body,      options),
  put:    (url, body, options)  => request('PUT',    url, body,      options),
  patch:  (url, body, options)  => request('PATCH',  url, body,      options),
  delete: (url, options)        => request('DELETE', url, undefined, options),
}

export default api
