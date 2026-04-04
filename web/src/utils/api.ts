/**
 * Thin fetch wrapper that redirects to login on 401.
 * All stores should use this instead of raw fetch() for authenticated endpoints.
 */

const LOGIN_URL = 'https://circuitforge.tech/login'

export async function apiFetch(url: string, init?: RequestInit): Promise<Response> {
  const res = await fetch(url, init)
  if (res.status === 401) {
    const next = encodeURIComponent(window.location.href)
    window.location.href = `${LOGIN_URL}?next=${next}`
    // Return a never-resolving promise — navigation is in progress
    return new Promise(() => {})
  }
  return res
}
