<script setup>
import { computed, ref, watch } from 'vue'
import Button from 'primevue/button'
import TreeTable from 'primevue/treetable'
import Column from 'primevue/column'
import Checkbox from 'primevue/checkbox'
import IconField from 'primevue/iconfield'
import InputIcon from 'primevue/inputicon'
import InputText from 'primevue/inputtext'
import Tag from 'primevue/tag'
import Message from 'primevue/message'
import Dialog from 'primevue/dialog'
import ToggleSwitch from 'primevue/toggleswitch'
import { useToast } from 'primevue/usetoast'
import OrgButton from './OrgButton.vue'
import { call, errorText } from '../api.js'
import { ago, orgLabel, plural } from '../format.js'
import { allKeysWithChildren, buildTree, filterTree } from '../sessionTree.js'
import { demo } from '../demo.js'

const props = defineProps({
  state: { type: Object, default: null },
  loading: { type: Boolean, default: false },
  titleSuffix: { type: String, default: '' },
})
const emit = defineEmits(['refresh', 'open-settings'])
const toast = useToast()

const orgs = computed(() => props.state?.orgs ?? [])
const srcId = ref(null)
const dstId = ref(null)
const src = computed(() => orgs.value.find((o) => o.id === srcId.value) ?? null)
const dst = computed(() => orgs.value.find((o) => o.id === dstId.value) ?? null)

const sessions = ref([])
const loadingSessions = ref(false)
const search = ref('')
const expanded = ref({})
const picked = ref(new Set()) // what the user ticked; sub-sessions of these come along automatically

const copying = ref(false)
const sync = ref(false)
const result = ref(null)

// ---------- tree + selection ----------
const tree = computed(() => buildTree(sessions.value))
const view = computed(() => filterTree(tree.value.roots, search.value))
const parentCount = computed(() => tree.value.roots.filter((n) => n.children.length).length)

const implied = computed(() => {
  const out = new Set()
  for (const id of picked.value) for (const d of tree.value.descendants.get(id) || []) out.add(d)
  return out
})
const total = computed(() => new Set([...picked.value, ...implied.value]).size)
const subIncluded = computed(() => [...implied.value].filter((id) => !picked.value.has(id)).length)

const isChecked = (id) => picked.value.has(id) || implied.value.has(id)
const isLocked = (id) => implied.value.has(id)

function toggle(id) {
  if (isLocked(id)) return
  const next = new Set(picked.value)
  if (next.has(id)) {
    next.delete(id)
  } else {
    next.add(id)
    for (const d of tree.value.descendants.get(id) || []) next.delete(d) // now covered by the parent
  }
  picked.value = next
}

// "Select all" picks the visible top-level rows (or, while searching, the matching rows).
const allTargets = computed(() => {
  const keys = search.value.trim() ? view.value.matches : view.value.nodes.map((n) => n.key)
  const set = new Set(keys)
  const parentOf = tree.value.parentOf
  const coveredByAncestor = (id) => {
    for (let p = parentOf.get(id); p; p = parentOf.get(p)) if (set.has(p)) return true
    return false
  }
  return keys.filter((k) => !coveredByAncestor(k))
})
const allState = computed(() => {
  const t = allTargets.value
  if (!t.length) return 'none'
  const n = t.filter(isChecked).length
  return n === 0 ? 'none' : n === t.length ? 'all' : 'some'
})
function toggleAll() {
  if (allState.value === 'all') {
    const drop = new Set(allTargets.value)
    picked.value = new Set([...picked.value].filter((id) => !drop.has(id)))
  } else {
    const next = new Set(picked.value)
    for (const id of allTargets.value) {
      next.add(id)
      for (const d of tree.value.descendants.get(id) || []) next.delete(d)
    }
    picked.value = next
  }
}

watch(search, (q) => {
  expanded.value = q.trim() ? allKeysWithChildren(view.value.nodes) : {}
})

// ---------- route ----------
// Keep the route valid whenever the list of orgs changes: default "from" is the busiest signed-in org.
watch(orgs, (list) => {
  if (!list.find((o) => o.id === srcId.value)) {
    const ranked = [...list].sort((a, b) => (b.signedIn - a.signedIn) || (b.sessionCount - a.sessionCount))
    srcId.value = ranked[0]?.id ?? null
  }
  if (!list.find((o) => o.id === dstId.value) || dstId.value === srcId.value) {
    dstId.value = list.find((o) => o.id !== srcId.value)?.id ?? null
  }
}, { immediate: true })

watch(srcId, async (id, old) => {
  if (id && id === dstId.value) dstId.value = old ?? orgs.value.find((o) => o.id !== id)?.id ?? null
  picked.value = new Set()
  sessions.value = []
  search.value = ''
  expanded.value = {}
  if (!id) return
  loadingSessions.value = true
  try {
    sessions.value = await call('get_sessions', id)
    if (demo === 'tree') {
      picked.value = new Set(['local_0', 'local_3'])
      expanded.value = { local_0: true, local_s2: true }
    }
  } catch (e) {
    toast.add({ severity: 'error', summary: 'Couldn’t load sessions', detail: errorText(e), life: 6000 })
  } finally {
    loadingSessions.value = false
  }
}, { immediate: true })

// ---------- copy ----------
const canCopy = computed(() => total.value > 0 && dst.value && !copying.value)
const copyLabel = computed(() => {
  if (!dst.value) return 'Add a destination first'
  if (!total.value) return 'Select sessions below'
  return `${sync.value ? 'Sync' : 'Copy'} ${plural(total.value, 'session')}`
})

async function copy() {
  if (!canCopy.value) return
  copying.value = true
  try {
    const [res, running] = await Promise.all([
      call('copy', srcId.value, dstId.value, [...picked.value], props.titleSuffix, sync.value),
      call('claude_running'),
    ])
    result.value = { ...res, to: orgLabel(dst.value), from: orgLabel(src.value), running, suffix: props.titleSuffix.trim(), subs: subIncluded.value, sync: sync.value }
    picked.value = new Set()
    emit('refresh')
  } catch (e) {
    toast.add({ severity: 'error', summary: 'Copy failed', detail: errorText(e), life: 8000 })
  } finally {
    copying.value = false
  }
}
</script>

<template>
  <div v-if="!state && loading" class="placeholder">Reading your Claude sessions…</div>

  <div v-else-if="!orgs.length" class="empty">
    <i class="pi pi-inbox empty-icon" aria-hidden="true" />
    <h2>No Claude Code sessions on this computer</h2>
    <p>Open the Claude desktop app, sign in, and start a session in the Code tab. Then reload.</p>
    <p v-if="state" class="muted small">Looked in {{ state.appDir }}</p>
    <div class="empty-actions">
      <Button label="Reload" icon="pi pi-refresh" @click="emit('refresh')" />
      <Button label="Choose Claude’s folder…" severity="secondary" outlined @click="emit('open-settings')" />
    </div>
  </div>

  <div v-else class="sessions-view">
    <section class="ticket" aria-label="Copy route">
      <div class="ticket-main">
        <OrgButton role="From" :org="src" :orgs="orgs" :disabled-id="null" @select="srcId = $event" />
        <div class="route" aria-hidden="true"><span class="route-line" /><i class="pi pi-arrow-right" /></div>
        <OrgButton role="To" :org="dst" :orgs="orgs" :disabled-id="srcId"
                   empty-text="No other organization yet" @select="dstId = $event" />
      </div>
      <div class="ticket-stub">
        <span class="eyebrow">Selected</span>
        <span class="stub-count" aria-live="polite">{{ total }}</span>
        <span class="stub-sub">{{ subIncluded ? `incl. ${plural(subIncluded, 'sub-session')}` : '' }}</span>
        <label class="sync-row" for="sync-toggle">
          <ToggleSwitch v-model="sync" input-id="sync-toggle" class="sync-switch" />
          <span>Keep in sync</span>
          <i v-tooltip.left="'Both organizations share one conversation. When you hit a usage limit in one, continue in the other, then switch back later and pick up the latest progress. Work in one at a time.'"
             class="pi pi-info-circle" tabindex="0" aria-label="What does keep in sync mean?" />
        </label>
        <Button class="stub-button" :label="copyLabel" :disabled="!canCopy" :loading="copying"
                :icon="canCopy ? 'pi pi-arrow-right' : undefined" icon-pos="right" @click="copy" />
      </div>
    </section>

    <Message v-if="!dst" severity="info" class="hint">
      To copy into another account or organization, sign in to it once in the Claude desktop app, then reload.
    </Message>

    <section class="list-card">
      <div class="table-head">
        <IconField class="search">
          <InputIcon class="pi pi-search" />
          <InputText v-model="search" placeholder="Search sessions or projects" aria-label="Search" />
        </IconField>
        <span class="muted small">
          {{ plural(sessions.length, 'session') }} in {{ orgLabel(src) }}<template v-if="parentCount"> · sub-sessions are grouped under the session that started them</template>
        </span>
        <Button v-if="picked.size" label="Clear selection" text size="small" severity="secondary"
                @click="picked = new Set()" />
      </div>

      <TreeTable v-model:expanded-keys="expanded" :value="view.nodes" scrollable scroll-height="flex"
                 :loading="loadingSessions" :indentation="1.6" class="sessions-tree" row-hover>
        <template #empty>
          <div class="table-empty">
            {{ search ? 'No sessions match your search.' : `${src ? orgLabel(src) : 'This organization'} has no Code sessions yet.` }}
          </div>
        </template>

        <Column expander>
          <template #header>
            <div class="head-select">
              <Checkbox :model-value="allState === 'all'" :indeterminate="allState === 'some'" binary
                        input-id="select-all" :disabled="!allTargets.length" @update:model-value="toggleAll" />
              <label for="select-all">Session</label>
            </div>
          </template>
          <template #body="{ node }">
            <div class="session-cell" :class="{ 'is-locked': isLocked(node.key) }">
              <Checkbox :model-value="isChecked(node.key)" binary :input-id="`s-${node.key}`"
                        :disabled="isLocked(node.key)" @update:model-value="toggle(node.key)" />
              <label :for="`s-${node.key}`" class="session-label">
                <span class="title-cell">{{ node.data.title }}</span>
                <span v-if="node.data.subCount" class="sub-count">
                  <i class="pi pi-sitemap" aria-hidden="true" />{{ plural(node.data.subCount, 'sub-session') }}
                </span>
                <span v-if="isLocked(node.key)" class="with-parent">Comes with parent</span>
                <span v-if="node.data.syncedWith?.length" v-tooltip.top="'Shares its conversation with this session in the other organization'"
                      class="synced-tag"><i class="pi pi-sync" aria-hidden="true" />Synced · {{ node.data.syncedWith.join(', ') }}</span>
                <Tag v-if="node.data.archived" value="Archived" severity="secondary" class="archived-tag" />
              </label>
            </div>
          </template>
        </Column>
        <Column field="project" header="Project" style="width: 24%">
          <template #body="{ node }">
            <span v-tooltip.top="node.data.cwd" class="project-cell"><i class="pi pi-folder" aria-hidden="true" />{{ node.data.project || '—' }}</span>
          </template>
        </Column>
        <Column field="lastActivity" header="Last used" style="width: 9.5rem">
          <template #body="{ node }"><span class="muted">{{ ago(node.data.lastActivity) }}</span></template>
        </Column>
      </TreeTable>
    </section>

    <Dialog :visible="!!result" modal :closable="false" :draggable="false" class="result-dialog"
            :style="{ width: '28rem' }" @update:visible="result = null">
      <template #container>
        <div v-if="result" class="result">
          <i class="pi pi-check-circle result-icon" aria-hidden="true" />
          <h2>{{ result.sync ? 'Synced' : 'Copied' }} {{ plural(result.copied, 'session') }} {{ result.sync ? 'with' : 'to' }} {{ result.to }}</h2>
          <p v-if="result.sync">
            {{ result.from }} and {{ result.to }} now continue the same conversations. When you hit a usage limit in one,
            switch organization in the Claude app and keep going. The other picks up the latest progress the next time you open it.
          </p>
          <Message v-if="result.sync" severity="warn" size="small">
            Work on a synced session in one organization at a time. Rewinding a synced session splits it off into its own copy.
          </Message>
          <p>
            <template v-if="result.subs">Sub-sessions are still grouped under their parent sessions. </template>
            <template v-if="result.running">Quit and reopen the Claude desktop app, then switch</template>
            <template v-else>Open the Claude desktop app and switch</template>
            to {{ result.to }} to see them<template v-if="result.suffix">, titled with “{{ result.suffix }}”</template>.
            <template v-if="!result.sync">The originals weren’t changed.</template>
          </p>
          <Message v-if="result.missingTranscripts" severity="warn" size="small">
            {{ plural(result.missingTranscripts, 'session') }} had no saved conversation on this computer, so only the title and settings were copied.
          </Message>
          <Button label="Done" class="result-done" autofocus @click="result = null" />
        </div>
      </template>
    </Dialog>
  </div>
</template>
