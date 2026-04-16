import { ref, watchEffect } from 'vue'

const LS_KEY  = 'snipe:theme'
type ThemeMode = 'system' | 'dark' | 'light'

// Module-level — shared across all callers
const mode = ref<ThemeMode>((localStorage.getItem(LS_KEY) as ThemeMode) ?? 'system')

function _apply(m: ThemeMode) {
  const el = document.documentElement
  if (m === 'dark') {
    el.dataset.theme = 'dark'
  } else if (m === 'light') {
    el.dataset.theme = 'light'
  } else {
    delete el.dataset.theme
  }
}

export function useTheme() {
  function setMode(m: ThemeMode) {
    mode.value = m
    localStorage.setItem(LS_KEY, m)
    _apply(m)
  }

  /** Re-apply from localStorage on hard reload (call from App.vue onMounted). */
  function restore() {
    _apply(mode.value)
  }

  return { mode, setMode, restore }
}
