import { createApp } from 'vue'
import PrimeVue from 'primevue/config'
import ToastService from 'primevue/toastservice'
import Tooltip from 'primevue/tooltip'
import Aura from '@primeuix/themes/aura'
import { definePreset } from '@primeuix/themes'

import '@fontsource-variable/hanken-grotesk'
import '@fontsource/martian-mono/500.css'
import '@fontsource/martian-mono/700.css'
import 'primeicons/primeicons.css'
import './style.css'
import App from './App.vue'

// Navy primary (the ticket) on cool grey surfaces. Brand orange is reserved for the route codes in style.css.
const Ticket = definePreset(Aura, {
  primitive: {
    borderRadius: { none: '0', xs: '4px', sm: '6px', md: '8px', lg: '10px', xl: '14px' },
  },
  semantic: {
    primary: {
      50: '#eef3f8', 100: '#d6e1ec', 200: '#adc3d9', 300: '#7f9fbf', 400: '#557ba1',
      500: '#365d84', 600: '#284a6b', 700: '#1e3a55', 800: '#172d43', 900: '#14263a', 950: '#0c1826',
    },
    colorScheme: {
      light: {
        primary: { color: '{primary.800}', contrastColor: '#ffffff', hoverColor: '{primary.900}', activeColor: '{primary.950}' },
        highlight: { background: '{primary.50}', focusBackground: '{primary.100}', color: '{primary.900}', focusColor: '{primary.950}' },
        surface: {
          0: '#ffffff', 50: '#f6f8fa', 100: '#eceff3', 200: '#dde2e8', 300: '#c6cdd6', 400: '#9aa5b2',
          500: '#687586', 600: '#4f5b69', 700: '#3a4450', 800: '#262e37', 900: '#16202b', 950: '#0d141c',
        },
      },
    },
  },
})

createApp(App)
  .use(PrimeVue, {
    theme: {
      preset: Ticket,
      // Always light: the ticket palette is designed for one scheme.
      options: { darkModeSelector: '.csc-dark-never', cssLayer: false },
    },
  })
  .use(ToastService)
  .directive('tooltip', Tooltip)
  .mount('#app')
