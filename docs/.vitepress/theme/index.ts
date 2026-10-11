import { h } from 'vue'
import DefaultTheme from 'vitepress/theme'
import type { Theme } from 'vitepress'
import VersionSwitcher from '@viteplus/versions/components/version-switcher.component.vue'
import VersionBanner from './VersionBanner.vue'

export default {
  extends: DefaultTheme,
  enhanceApp({ app }) {
    app.component('VersionSwitcher', VersionSwitcher)
  },
  Layout: () =>
    h(DefaultTheme.Layout, null, {
      'layout-top': () => h(VersionBanner),
    }),
} satisfies Theme
