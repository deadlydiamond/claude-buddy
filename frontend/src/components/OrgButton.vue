<script setup>
// One end of the route on the ticket: shows an organization by name (or its short code if the name
// couldn't be read) and opens a picker on click.
import { computed, ref } from 'vue'
import Popover from 'primevue/popover'
import Listbox from 'primevue/listbox'
import { orgLabel, plural } from '../format.js'

const props = defineProps({
  role: { type: String, required: true }, // 'From' | 'To'
  org: { type: Object, default: null },
  orgs: { type: Array, default: () => [] },
  disabledId: { type: String, default: null },
  emptyText: { type: String, default: 'None' },
})
const emit = defineEmits(['select'])
const pop = ref()

const options = computed(() => props.orgs.map((o) => ({ ...o, disabled: o.id === props.disabledId })))
const accountText = (o) => o.email || (o.signedIn ? 'Signed-in account' : `Account ${o.accountCode}`)

function choose(e) {
  if (e.value) emit('select', e.value)
  pop.value.hide()
}
</script>

<template>
  <div class="end">
    <span class="eyebrow">{{ role }}</span>
    <button v-if="org" class="end-button" type="button" :aria-label="`${role}: ${orgLabel(org)}. Change`"
            @click="pop.toggle($event)">
      <span class="org-title">
        <span :class="org.name ? 'org-name' : 'code'">{{ orgLabel(org) }}</span>
        <i class="pi pi-chevron-down" aria-hidden="true" />
      </span>
      <span class="end-account">
        <span v-if="org.plan" class="plan-pill">{{ org.plan }}</span>
        <span class="end-email">{{ accountText(org) }}</span>
      </span>
      <span class="end-hint">{{ plural(org.sessionCount, 'session') }}<template v-if="org.latestTitle"> · Latest: {{ org.latestTitle }}</template></span>
    </button>
    <div v-else class="end-empty">
      <span class="code code-empty">----</span>
      <span class="end-account"><span class="end-email">{{ emptyText }}</span></span>
    </div>

    <Popover ref="pop">
      <div class="picker">
        <div class="picker-title">Copy {{ role.toLowerCase() }}</div>
        <Listbox :model-value="org?.id" :options="options" option-value="id" option-disabled="disabled"
                 data-key="id" class="picker-list" @change="choose">
          <template #option="{ option }">
            <div class="picker-option">
              <span class="picker-icon" :class="{ team: option.plan && !option.personal }" aria-hidden="true">
                <i :class="option.personal ? 'pi pi-user' : 'pi pi-users'" />
              </span>
              <div class="picker-text">
                <div class="picker-line">
                  <span class="picker-name">{{ orgLabel(option) }}</span>
                  <span v-if="option.plan" class="picker-plan">{{ option.plan }}</span>
                </div>
                <div class="picker-hint">
                  <template v-if="option.disabled">You’re copying from here</template>
                  <template v-else>{{ accountText(option) }} · {{ plural(option.sessionCount, 'session') }}</template>
                </div>
              </div>
            </div>
          </template>
        </Listbox>
      </div>
    </Popover>
  </div>
</template>
