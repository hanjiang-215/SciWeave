import { createPinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { createMemoryHistory } from 'vue-router'
import App from '@/App.vue'
import { createAppRouter } from '@/router'

vi.mock('@/data/fixtureQuery', () => ({
  fixtureQuery: {
    getSnapshot: async () => ({
      mode: 'live',
      observedAt: '2026-10-22T10:00:00Z',
      sources: [{ id: 'mapping', label: 'Research Mapping', status: 'fresh', observedAt: '2026-10-22T10:00:00Z' }],
      projects: [], tasks: [], wikiDocuments: [], wikiCandidates: [], executions: [], services: [], events: [], partial: false,
    }),
  },
}))

describe('empty dashboard', () => {
  it('distinguishes a confirmed empty workspace from missing data sources', async () => {
    const router = createAppRouter(createMemoryHistory())
    await router.push('/')
    await router.isReady()
    const wrapper = mount(App, { global: { plugins: [createPinia(), router] } })
    await flushPromises()
    expect(wrapper.text()).toContain('目前没有研究记录')
    expect(wrapper.text()).toContain('与来源不可用不同')
    expect(wrapper.text()).not.toContain('数据暂不可用')
  })
})
