<script setup>
import { computed, ref } from 'vue'
import Button from 'primevue/button'
import Message from 'primevue/message'
import { useToast } from 'primevue/usetoast'
import { call, errorText } from '../api.js'
import { plural } from '../format.js'
import { demo } from '../demo.js'

const toast = useToast()
const exportPath = ref(demo === 'chats' ? '/Users/you/Downloads/data-2026-10-19-claude.zip' : '')
const converting = ref(false)
const done = ref(demo === 'chats' ? { chats: 42, projects: 3, out: '/Users/you/Downloads/data-2026-10-19-claude-markdown' } : null)
const fileName = computed(() => exportPath.value.split(/[\\/]/).pop())

async function choose() {
  const p = await call('pick_export')
  if (p) {
    exportPath.value = p
    done.value = null
  }
}

async function convert() {
  converting.value = true
  try {
    done.value = await call('convert_export', exportPath.value)
  } catch (e) {
    toast.add({ severity: 'error', summary: 'Couldn’t convert that file', detail: errorText(e), life: 8000 })
  } finally {
    converting.value = false
  }
}
</script>

<template>
  <div class="chats-view">
    <div class="chats-intro">
      <h1>Bring your claude.ai chats to another account</h1>
      <p>Claude can’t import chats directly. Instead, turn your export into readable files and add them to a Project in the new account, so Claude can refer back to them.</p>
    </div>

    <ol class="steps">
      <li class="step">
        <span class="step-num">1</span>
        <div class="step-body">
          <h3>Download your data from claude.ai</h3>
          <p>In the account you’re leaving, open Settings → Privacy → Export data. Claude emails you a link to a .zip file.</p>
        </div>
        <Button label="Open claude.ai settings" icon="pi pi-external-link" icon-pos="right" severity="secondary" outlined
                @click="call('open_url', 'https://claude.ai/settings/data-privacy-controls')" />
      </li>

      <li class="step">
        <span class="step-num" :class="{ 'is-done': exportPath }"><i v-if="exportPath" class="pi pi-check" /><template v-else>2</template></span>
        <div class="step-body">
          <h3>Choose the downloaded .zip</h3>
          <p v-if="exportPath" class="file-chip"><i class="pi pi-file" aria-hidden="true" />{{ fileName }}</p>
          <p v-else>It’s usually in your Downloads folder and named like data-2026-10-19.zip.</p>
        </div>
        <Button :label="exportPath ? 'Choose another…' : 'Choose .zip…'" severity="secondary" outlined @click="choose" />
      </li>

      <li class="step">
        <span class="step-num" :class="{ 'is-done': done }"><i v-if="done" class="pi pi-check" /><template v-else>3</template></span>
        <div class="step-body">
          <h3>Convert to Markdown</h3>
          <p>Creates a folder of chats next to the .zip. Then create a Project in your new account and upload the chats you want Claude to remember.</p>
        </div>
        <Button label="Convert" :disabled="!exportPath" :loading="converting" @click="convert" />
      </li>
    </ol>

    <Message v-if="done" severity="success" class="done-msg">
      <div class="done-row">
        <span>Saved {{ plural(done.chats, 'chat') }} and {{ plural(done.projects, 'project') }} to <b>{{ done.out.split(/[\\/]/).pop() }}</b>.</span>
        <Button label="Show folder" size="small" severity="success" text @click="call('reveal', done.out)" />
      </div>
    </Message>
  </div>
</template>
