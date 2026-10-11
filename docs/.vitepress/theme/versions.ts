import type { DefaultTheme } from 'vitepress/theme'

export type ThemeConfig = DefaultTheme.Config & { docsVersion: string; archivedVersions: string[] }

export type Banner = { kind: 'dev' } | { kind: 'outdated'; version: string; latest: string; link: string }

export const RELEASE = /^v\d+\.\d+\.\d+$/

export function bannerFor(path: string, docsVersion: string, archived: string[]): Banner | null {
  const version = path.split('/')[1]
  if (!archived.includes(version)) return docsVersion === 'dev' ? { kind: 'dev' } : null
  // A release build serves the latest release at the root; other builds have it as their newest archive.
  const isRelease = RELEASE.test(docsVersion)
  const latest = isRelease ? docsVersion : archived[0]
  if (version === latest) return null
  return { kind: 'outdated', version, latest, link: isRelease ? '/' : `/${latest}/` }
}
