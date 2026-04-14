// composables/useTrustSignalPref.ts
// User opt-in for showing "This score looks right / wrong" trust signal buttons.
// Off by default — users explicitly enable it in Settings.
import { ref } from 'vue'

const LS_KEY = 'snipe:trust-signal-enabled'

const enabled = ref(localStorage.getItem(LS_KEY) === 'true')

export function useTrustSignalPref() {
  function setEnabled(value: boolean) {
    enabled.value = value
    localStorage.setItem(LS_KEY, value ? 'true' : 'false')
  }

  return { enabled, setEnabled }
}
