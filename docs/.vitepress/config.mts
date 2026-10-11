import { existsSync, readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { defineVersionedConfig } from '@viteplus/versions'
import type { DefaultTheme } from 'vitepress'
import navigation from './navigation.json'
import referenceSidebar from './reference-sidebar.json'
import { RELEASE } from './theme/versions'

type Navigation = { nav: DefaultTheme.NavItem[]; sidebar: Record<string, DefaultTheme.SidebarItem[]> }

const docsVersion = process.env.DOCS_VERSION ?? 'dev'
const archive = join(import.meta.dirname, '..', 'archive')

function newestFirst(a: string, b: string): number {
  const [left, right] = [a, b].map((version) => version.slice(1).split('.').map(Number))
  const index = left.findIndex((part, i) => part !== right[i])
  return index === -1 ? 0 : right[index] - left[index]
}

const archivedVersions = existsSync(archive)
  ? readdirSync(archive).filter((name) => RELEASE.test(name)).sort(newestFirst)
  : []

const archived: Record<string, Navigation> = Object.fromEntries(
  archivedVersions.map((version) => [version, JSON.parse(readFileSync(join(archive, version, 'navigation.json'), 'utf8'))]),
)

const switcher = { component: 'VersionSwitcher', props: { latestLabel: RELEASE.test(docsVersion) ? 'latest' : '' } }

// https://vitepress.dev/reference/site-config
export default defineVersionedConfig({
  title: "Strawchemy",
  description: "Generate GraphQL API from SQLAlchemy models",
  srcExclude: ['superpowers/**'],
  versionsConfig: { current: docsVersion, versionSwitcher: false },
  themeConfig: {
    // https://vitepress.dev/reference/default-theme-config
    docsVersion,
    archivedVersions,
    nav: {
      root: [...navigation.nav, switcher],
      ...Object.fromEntries(archivedVersions.map((version) => [version, [...archived[version].nav, switcher]])),
    },
    sidebar: {
      ...navigation.sidebar,
      '/reference/': referenceSidebar,
      ...Object.fromEntries(
        archivedVersions.flatMap((version) =>
          Object.entries(archived[version].sidebar).map(([path, items]) => [`/${version}${path}`, items]),
        ),
      ),
    },
    outline: { level: [2, 3], label: 'On this page' },
    search: { provider: 'local' },
    socialLinks: [
      { icon: 'github', link: 'https://github.com/gazorby/strawchemy' }
    ]
  }
})
