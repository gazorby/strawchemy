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
      { text: 'Learn', link: '/learn/' },
      { text: 'Reference', link: '/reference/api/mapper' },
    ],
    sidebar: {
      '/learn/': [
        {
          text: 'Introduction',
          collapsed: false,
          items: [
            { text: 'Strawchemy', link: '/learn/' },
            { text: 'Strawchemy and Strawberry', link: '/learn/strawchemy-and-strawberry' },
            { text: 'Getting started', link: '/learn/getting-started' },
          ],
        },
        {
          text: 'Schema',
          collapsed: false,
          items: [
            { text: 'Mapping models', link: '/learn/mapping-models' },
            { text: 'Configuration', link: '/learn/configuration' },
          ],
        },
        {
          text: 'Querying',
          collapsed: false,
          items: [
            { text: 'Queries', link: '/learn/queries' },
            { text: 'Filtering', link: '/learn/filtering' },
            { text: 'Ordering', link: '/learn/ordering' },
            { text: 'Pagination', link: '/learn/pagination' },
            { text: 'Aggregations', link: '/learn/aggregations' },
            { text: 'Custom resolvers', link: '/learn/resolvers' },
            { text: 'Query hooks', link: '/learn/query-hooks' },
          ],
        },
        {
          text: 'Mutating',
          collapsed: false,
          items: [
            { text: 'Mutations', link: '/learn/mutations/' },
            { text: 'Create', link: '/learn/mutations/create' },
            { text: 'Nested create', link: '/learn/mutations/relationships-create' },
            { text: 'Update', link: '/learn/mutations/update' },
            { text: 'Nested update', link: '/learn/mutations/relationships-update' },
            { text: 'Delete', link: '/learn/mutations/delete' },
            { text: 'Upsert', link: '/learn/mutations/upsert' },
            { text: 'Validation', link: '/learn/mutations/validation' },
          ],
        },
        {
          text: 'Advanced',
          collapsed: false,
          items: [
            { text: 'Architecture', link: '/learn/architecture' },
            { text: 'Geometry', link: '/learn/geometry' },
            { text: 'Async sessions', link: '/learn/async' },
          ],
        },
      ],
      '/reference/': referenceSidebar,
    },
    outline: { level: [2, 3], label: 'On this page' },
    search: { provider: 'local' },
    socialLinks: [
      { icon: 'github', link: 'https://github.com/gazorby/strawchemy' }
    ]
  }
})
