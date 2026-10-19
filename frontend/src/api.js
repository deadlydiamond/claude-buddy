// Bridge to the Python side (claude_session_copy/app.py → class Api).
// Inside the desktop app pywebview injects window.pywebview.api. In `npm run dev` (a plain browser)
// there is no Python, so a mock with sample data is used instead. Production builds never use the mock.

import { mock } from './mock.js'

const ready = new Promise((resolve) => {
  if (window.pywebview?.api) return resolve(window.pywebview.api)
  window.addEventListener('pywebviewready', () => resolve(window.pywebview.api), { once: true })
  if (import.meta.env.DEV) setTimeout(() => resolve(null), 400)
})

export async function call(name, ...args) {
  const api = await ready
  if (!api) return mock[name](...args)
  return api[name](...args)
}

export function errorText(e) {
  if (!e) return 'Something went wrong.'
  if (typeof e === 'string') return e
  return e.message || String(e)
}
