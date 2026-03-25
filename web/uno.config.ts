import { defineConfig, presetWind, presetAttributify } from 'unocss'

export default defineConfig({
  presets: [
    presetWind(),
    // prefixedOnly: avoids false-positive CSS for bare attribute names like "h2", "grid",
    // "shadow" in source files. Use <div un-flex> not <div flex>. Gotcha #4.
    presetAttributify({ prefix: 'un-', prefixedOnly: true }),
  ],
  // Snipe-specific theme tokens are defined as CSS custom properties in
  // src/assets/theme.css — see that file for the full dark tactical palette.
  // UnoCSS config is kept minimal; all colour decisions use var(--...) tokens.
})
