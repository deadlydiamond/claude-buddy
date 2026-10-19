<script setup>
import { onMounted, ref } from 'vue'
import Button from 'primevue/button'
import SelectButton from 'primevue/selectbutton'
import Toast from 'primevue/toast'
import { useToast } from 'primevue/usetoast'
import SessionsView from './components/SessionsView.vue'
import ChatsView from './components/ChatsView.vue'
import SettingsDialog from './components/SettingsDialog.vue'
import { call, errorText } from './api.js'
import { demo } from './demo.js'
import logo from './logo.png'

const toast = useToast()
const mode = ref(demo === 'chats' ? 'chats' : 'sessions')
const modes = [
  { label: 'Code sessions', value: 'sessions' },
  { label: 'claude.ai chats', value: 'chats' },
]
const state = ref(null)
const loading = ref(true)
const settingsOpen = ref(false)
const titleSuffix = ref(' (copied)')

async function refresh() {
  loading.value = true
  try {
    state.value = await call('get_state')
  } catch (e) {
    toast.add({ severity: 'error', summary: 'Couldn’t read Claude’s data', detail: errorText(e), life: 6000 })
  } finally {
    loading.value = false
  }
}

async function saveSettings({ appDir, configDir, suffix }) {
  titleSuffix.value = suffix
  try {
    state.value = await call('set_folders', appDir, configDir)
    settingsOpen.value = false
  } catch (e) {
    toast.add({ severity: 'error', summary: 'Couldn’t use those folders', detail: errorText(e), life: 6000 })
  }
}

onMounted(refresh)
</script>

<template>
  <div class="shell">
    <header class="topbar">
      <div class="brand"><img :src="logo" alt="" width="26" height="26">Claude Buddy</div>
      <SelectButton v-model="mode" :options="modes" option-label="label" option-value="value" :allow-empty="false"
                    aria-label="What to copy" />
      <div class="top-actions">
        <Button v-tooltip.bottom="'Reload sessions'" icon="pi pi-refresh" text rounded severity="secondary"
                aria-label="Reload sessions" :loading="loading" @click="refresh" />
        <Button v-tooltip.bottom="'Settings'" icon="pi pi-cog" text rounded severity="secondary"
                aria-label="Settings" @click="settingsOpen = true" />
      </div>
    </header>

    <main class="content">
      <SessionsView v-if="mode === 'sessions'" :state="state" :loading="loading" :title-suffix="titleSuffix"
                    @refresh="refresh" @open-settings="settingsOpen = true" />
      <ChatsView v-else />
    </main>

    <SettingsDialog v-if="state" v-model:visible="settingsOpen" :app-dir="state.appDir" :config-dir="state.configDir"
                    :suffix="titleSuffix" @save="saveSettings" />
    <Toast position="bottom-center" />
  </div>
</template>
