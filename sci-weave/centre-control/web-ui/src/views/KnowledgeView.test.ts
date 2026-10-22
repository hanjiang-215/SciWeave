import { createPinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import App from '@/App.vue'
import { createMemoryHistory } from 'vue-router'
import { createAppRouter } from '@/router'

it('separates formal Wiki documents from pending candidates and shows exact resource qualifications', async () => {
  const router = createAppRouter(createMemoryHistory())
  await router.push('/knowledge')
  await router.isReady()
  const wrapper = mount(App, { global: { plugins: [createPinia(), router] } })
  await flushPromises()
  expect(wrapper.text()).toContain('知识与候选')
  expect(wrapper.text()).toContain('已发布正式版本')
  expect(wrapper.text()).toContain('候选待审核')
  expect(wrapper.text()).toContain('ResourceVersion · rv-2026-041')
  expect(wrapper.text()).toContain('资格待确认')
  expect(wrapper.text()).toContain('不显示为正式版本')
})
