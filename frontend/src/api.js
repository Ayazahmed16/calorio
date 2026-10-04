export const BASE = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000/api'

export async function login(username, password) {
  const res = await fetch(`${BASE}/token/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
  if (!res.ok) throw new Error('Wrong username or password')
  const data = await res.json()
  return data.token
}

export async function api(path, token, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Token ${token}`,
    },
  })
  if (res.status === 204) return null
  if (!res.ok) throw new Error('Request failed')
  return res.json()
}