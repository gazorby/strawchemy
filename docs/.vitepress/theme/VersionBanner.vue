<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { useData, useRoute } from 'vitepress'
import { bannerFor, type ThemeConfig } from './versions'

const { theme } = useData<ThemeConfig>()
const route = useRoute()
const banner = ref<HTMLElement>()
const message = computed(() => bannerFor(route.path, theme.value.docsVersion, theme.value.archivedVersions))

// The default theme offsets its fixed nav and sidebar by --vp-layout-top-height, so it must track the
// banner's rendered height, which grows when the message wraps on narrow screens.
const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(([entry]) => setTopHeight(entry.target))

function setTopHeight(element: Element | undefined) {
  const style = document.documentElement.style
  if (element) style.setProperty('--vp-layout-top-height', `${(element as HTMLElement).offsetHeight}px`)
  else style.removeProperty('--vp-layout-top-height')
}

watch(banner, (element, previous) => {
  if (previous) observer?.unobserve(previous)
  if (element) observer?.observe(element)
  setTopHeight(element)
})

onUnmounted(() => {
  observer?.disconnect()
  setTopHeight(undefined)
})
</script>

<template>
  <div v-if="message?.kind === 'dev'" ref="banner" class="version-banner">
    Documentation for unreleased <code>main</code>. <a href="https://strawchemy.pages.dev/">See the latest release</a>
  </div>
  <div v-else-if="message?.kind === 'outdated'" ref="banner" class="version-banner">
    Documentation for {{ message.version }}. The latest release is {{ message.latest }}.
    <a :href="message.link">Go to {{ message.latest }}</a>
  </div>
</template>

<style scoped>
.version-banner {
  position: fixed;
  top: 0;
  right: 0;
  left: 0;
  z-index: var(--vp-z-index-layout-top);
  padding: 8px 24px;
  text-align: center;
  font-size: 14px;
  line-height: 24px;
  color: var(--vp-c-text-1);
  background: linear-gradient(var(--vp-c-warning-soft), var(--vp-c-warning-soft)), var(--vp-c-bg);
}

.version-banner a {
  font-weight: 500;
  color: var(--vp-c-brand-1);
  text-decoration: underline;
}
</style>
