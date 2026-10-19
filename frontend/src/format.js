export function ago(ms) {
  if (!ms) return ''
  const s = (Date.now() - ms) / 1000
  if (s < 60) return 'Just now'
  if (s < 3600) return `${Math.floor(s / 60)} min ago`
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`
  if (s < 2 * 86400) return 'Yesterday'
  if (s < 7 * 86400) return `${Math.floor(s / 86400)} days ago`
  const d = new Date(ms)
  const sameYear = d.getFullYear() === new Date().getFullYear()
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', ...(sameYear ? {} : { year: 'numeric' }) })
}

export const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`

// Organizations are shown by name ("Developers-77o", "Personal"); the short code is the fallback.
export const orgLabel = (o) => (o ? o.name || o.code : '')
