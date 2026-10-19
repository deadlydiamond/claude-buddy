<script setup>
import { ref, watch } from 'vue'
import Button from 'primevue/button'
import Dialog from 'primevue/dialog'
import InputText from 'primevue/inputtext'
import InputGroup from 'primevue/inputgroup'
import { call } from '../api.js'

const props = defineProps({ appDir: String, configDir: String, suffix: String })
const visible = defineModel('visible', { type: Boolean })
const emit = defineEmits(['save'])

const appDir = ref('')
const configDir = ref('')
const suffix = ref('')
watch(visible, (v) => {
  if (v) {
    appDir.value = props.appDir
    configDir.value = props.configDir
    suffix.value = props.suffix
  }
}, { immediate: true })

const fields = { app: appDir, config: configDir }
async function browse(which) {
  const target = fields[which]
  const p = await call('pick_folder', target.value)
  if (p) target.value = p
}
</script>

<template>
  <Dialog v-model:visible="visible" modal header="Settings" :style="{ width: '34rem' }" :draggable="false">
    <div class="settings">
      <label class="field">
        <span class="field-label">Add to copied session titles</span>
        <InputText v-model="suffix" placeholder="Leave empty to keep titles as they are" />
        <span class="field-help">Helps you tell copies apart from the originals.</span>
      </label>

      <div class="settings-divider">Claude’s folders <span class="muted">· found automatically</span></div>

      <label class="field">
        <span class="field-label">Claude desktop app data</span>
        <InputGroup>
          <InputText v-model="appDir" />
          <Button label="Change…" severity="secondary" outlined @click="browse('app')" />
        </InputGroup>
      </label>
      <label class="field">
        <span class="field-label">Claude Code conversations</span>
        <InputGroup>
          <InputText v-model="configDir" />
          <Button label="Change…" severity="secondary" outlined @click="browse('config')" />
        </InputGroup>
      </label>
    </div>
    <template #footer>
      <Button label="Cancel" severity="secondary" text @click="visible = false" />
      <Button label="Save" @click="emit('save', { appDir, configDir, suffix })" />
    </template>
  </Dialog>
</template>
