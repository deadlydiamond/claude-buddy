// Turns the flat session list into PrimeVue TreeTable nodes (sub-sessions under the session that started them)
// and works out which sessions a selection really copies: picking a parent always brings its sub-sessions.

export function buildTree(sessions) {
  const byId = new Map(sessions.map((s) => [s.id, s]))
  const kids = new Map()
  for (const s of sessions) {
    if (s.parentId && s.parentId !== s.id && byId.has(s.parentId)) {
      if (!kids.has(s.parentId)) kids.set(s.parentId, [])
      kids.get(s.parentId).push(s)
    }
  }
  const descendants = new Map() // id -> every id below it
  const parentOf = new Map()

  const build = (s, seen) => {
    const children = (kids.get(s.id) || [])
      .filter((k) => !seen.has(k.id))
      .map((k) => {
        parentOf.set(k.id, s.id)
        return build(k, new Set([...seen, k.id]))
      })
      .sort((a, b) => b.data.latest - a.data.latest)
    const below = children.flatMap((c) => [c.key, ...descendants.get(c.key)])
    descendants.set(s.id, below)
    const latest = Math.max(s.lastActivity || 0, ...children.map((c) => c.data.latest))
    return { key: s.id, data: { ...s, latest, subCount: below.length }, children, leaf: !children.length }
  }

  const roots = sessions
    .filter((s) => !s.parentId || !byId.has(s.parentId) || s.parentId === s.id)
    .map((s) => build(s, new Set([s.id])))
    .sort((a, b) => b.data.latest - a.data.latest)

  return { roots, descendants, parentOf }
}

// Keep nodes that match the query, plus the ancestors needed to reach them.
export function filterTree(nodes, query) {
  const q = query.trim().toLowerCase()
  if (!q) return { nodes, matches: [] }
  const matches = []
  const walk = (list) => list.flatMap((n) => {
    const hit = n.data.title.toLowerCase().includes(q) || (n.data.project || '').toLowerCase().includes(q)
    if (hit) matches.push(n.key)
    const children = walk(n.children)
    return hit || children.length ? [{ ...n, children: hit ? n.children : children }] : []
  })
  return { nodes: walk(nodes), matches }
}

export function allKeysWithChildren(nodes, out = {}) {
  for (const n of nodes) {
    if (n.children.length) {
      out[n.key] = true
      allKeysWithChildren(n.children, out)
    }
  }
  return out
}
