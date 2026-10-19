// Sample data for `npm run dev` in a browser. Not included in the desktop app's behaviour.

const now = Date.now()
const h = 3600_000

const orgs = [
  { id: 'a1173955-722b-4fe6-bad2-741f8a61d4a4', code: 'A117', name: 'Acme Engineering', plan: 'Team', personal: false, email: 'you@example.com', account: 'a575bae2', accountCode: 'A575', signedIn: true,
    sessionCount: 14, latestTitle: 'Image editor with layers and history', lastActivity: now - 2 * h },
  { id: 'fc1a760d-280f-4f4d-8574-6d756c80d2ae', code: 'FC1A', name: 'Personal', plan: 'Max', personal: true, email: 'you@example.com', account: 'a575bae2', accountCode: 'A575', signedIn: true,
    sessionCount: 3, latestTitle: 'Release checklist for v2', lastActivity: now - 26 * h },
  { id: 'b91a1e9d-6014-42b6-989e-7d46729036a4', code: 'B91A', name: 'Personal', plan: 'Pro', personal: true, email: 'you@side-project.dev', account: 'c30a14e9', accountCode: 'C30A', signedIn: false,
    sessionCount: 0, latestTitle: '', lastActivity: 0 },
]

const titles = [
  ['Image editor with layers and history', '/Users/me/code/studio-web', 2],
  ['Fix flaky checkout test on CI', '/Users/me/code/shop-api', 5],
  ['Migrate auth to OAuth device flow', '/Users/me/code/shop-api', 9],
  ['Dark mode for settings screens', '/Users/me/code/studio-mobile', 20],
  ['Postgres slow query investigation', '/Users/me/code/shop-api', 30],
  ['Landing page hero copy pass', '/Users/me/code/marketing-site', 50],
  ['Upgrade to Vite 8 and fix warnings', '/Users/me/code/studio-web', 80],
  ['Nightly backup script for uploads', '/Users/me/code/ops', 200],
  ['Prototype: voice notes transcription', '/Users/me/code/labs', 900],
]

const subs = [
  ['Layers panel drag-and-drop', '/Users/me/code/studio-web', 2.2, 'local_0'],
  ['Undo history persistence', '/Users/me/code/studio-web', 2.5, 'local_0'],
  ['Blend modes in the WebGL renderer', '/Users/me/code/studio-web', 3, 'local_0'],
  ['Snapshot tests for blend modes', '/Users/me/code/studio-web', 3.2, 'local_s2'],
  ['Token refresh race on mobile', '/Users/me/code/shop-api', 9.5, 'local_2'],
]

const sessions = {
  [orgs[0].id]: [
    ...titles.map(([title, cwd, ago], i) => ({
      id: `local_${i}`, title, cwd, project: cwd.split('/').pop(), lastActivity: now - ago * h, archived: i === 8, parentId: null, syncedWith: i === 1 ? ['Personal'] : [],
    })),
    ...subs.map(([title, cwd, ago, parentId], i) => ({
      id: `local_s${i}`, title, cwd, project: cwd.split('/').pop(), lastActivity: now - ago * h, archived: false, parentId,
    })),
  ],
  [orgs[1].id]: [
    { id: 'local_x1', title: 'Release checklist for v2', cwd: '/Users/me/code/ops', project: 'ops', lastActivity: now - 26 * h, archived: false },
  ],
  [orgs[2].id]: [],
}

const wait = (ms) => new Promise((r) => setTimeout(r, ms))

export const mock = {
  async get_state() {
    return { version: 'dev', appDir: '~/Library/Application Support/Claude', configDir: '~/.claude', found: true,
      multipleAccounts: true, orgs }
  },
  async get_sessions(id) { return sessions[id] || [] },
  async set_folders() { return this.get_state() },
  async copy(_s, _d, ids) { await wait(900); return { copied: ids.length, missingTranscripts: 0 } },
  async convert_export(p) { await wait(900); return { chats: 42, projects: 3, out: p.replace(/\.zip$/, '') + '-markdown' } },
  async pick_folder() { return '/Users/me/Library/Application Support/Claude' },
  async pick_export() { return '/Users/me/Downloads/data-2026-10-19-claude.zip' },
  async reveal() {},
  async open_url(u) { window.open(u, '_blank') },
  async claude_running() { return true },
}
