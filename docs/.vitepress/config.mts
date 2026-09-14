import { defineConfig } from 'vitepress'
import referenceSidebar from './reference-sidebar.json'

// https://vitepress.dev/reference/site-config
export default defineConfig({
  title: "Strawchemy",
  description: "Generate GraphQL API from SQLAlchemy models",
  srcExclude: ['superpowers/**'],
  themeConfig: {
    // https://vitepress.dev/reference/default-theme-config
    nav: [
      { text: 'Guide', link: '/guide/getting-started' },
      { text: 'Reference', link: '/reference/api/mapper' },
    ],
    sidebar: {
      '/guide/': [
        {
          text: 'Guide',
          collapsed: false,
          items: [
            { text: 'Getting started', link: '/guide/getting-started' },
            { text: 'Mapping models', link: '/guide/mapping-models' },
            { text: 'Resolvers', link: '/guide/resolvers' },
            { text: 'Pagination', link: '/guide/pagination' },
            { text: 'Ordering', link: '/guide/ordering' },
            { text: 'Filtering', link: '/guide/filtering' },
            { text: 'Aggregations', link: '/guide/aggregations' },
            { text: 'Async support', link: '/guide/async' },
            { text: 'Configuration', link: '/guide/configuration' },
          ],
        },
        {
          text: 'Mutations',
          collapsed: false,
          items: [
            { text: 'Overview', link: '/guide/mutations/' },
            { text: 'Create', link: '/guide/mutations/create' },
            { text: 'Create with relationships', link: '/guide/mutations/relationships-create' },
            { text: 'Update', link: '/guide/mutations/update' },
            { text: 'Update with relationships', link: '/guide/mutations/relationships-update' },
            { text: 'Delete', link: '/guide/mutations/delete' },
            { text: 'Upsert', link: '/guide/mutations/upsert' },
            { text: 'Validation', link: '/guide/mutations/validation' },
          ],
        },
      ],
      '/reference/': referenceSidebar,
    },
    search: { provider: 'local' },
    socialLinks: [
      { icon: 'github', link: 'https://github.com/gazorby/strawchemy' }
    ]
  }
})
