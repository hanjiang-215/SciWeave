import { createPinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import App from '@/App.vue'
import { createMemoryHistory } from 'vue-router'
import { createAppRouter } from '@/router'

async function renderAt(path: string) {
  const router = createAppRouter(createMemoryHistory())
  await router.push(path)
  await router.isReady()
  const wrapper = mount(App, { global: { plugins: [createPinia(), router] } })
  await flushPromises()
  return { wrapper, router }
}

describe('dashboard views', () => {
  it('shows project progress, attention items and listener health on overview', async () => {
    const { wrapper } = await renderAt('/')
    expect(wrapper.text()).toContain('催化剂筛选路线')
    expect(wrapper.text()).toContain('需要关注')
    expect(wrapper.text()).toContain('Centre Agent 消息监听')
    expect(wrapper.text()).toContain('部分数据')
  })

  it('shows task dependencies, blocker and stable detail navigation', async () => {
    const { wrapper, router } = await renderAt('/route?status=waiting')
    // The filtered task renders in the default map view with its blocker and owner.
    expect(wrapper.text()).toContain('等待 Project Owner 审核候选变化')
    expect(wrapper.text()).toContain('负责人：研究员 B')
    // Switching to the list view keeps the original dependency labels.
    await wrapper.get('button[role="tab"]:nth-child(2)').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('前置任务')
    await router.push('/tasks/task-validation')
    await flushPromises()
    expect(wrapper.text()).toContain('验证模型')
    expect(wrapper.text()).toContain('远端结果未知')
  })

  it('keeps status filters in the URL for repeatable links', async () => {
    const { wrapper, router } = await renderAt('/route')
    await wrapper.get('select[aria-label="按状态筛选任务"]').setValue('waiting')
    await flushPromises()
    expect(router.currentRoute.value.query.status).toBe('waiting')
    expect(wrapper.text()).toContain('等待 Project Owner 审核候选变化')
  })

  it('shows failures, unknown outcomes, duplicate messages and service freshness', async () => {
    const { wrapper } = await renderAt('/operations')
    expect(wrapper.text()).toContain('结果未知')
    expect(wrapper.text()).toContain('重复交接消息已被幂等处理')
    expect(wrapper.text()).toContain('query_execution')
    expect(wrapper.text()).toContain('最近一次状态检查已过期')
  })

  it('lets a user enable and choose an automatic refresh interval', async () => {
    const { wrapper } = await renderAt('/')
    const toggle = wrapper.get('input[aria-label="自动刷新"]')
    await toggle.setValue(true)
    expect(wrapper.find('select[aria-label="自动刷新间隔"]').exists()).toBe(true)
    await wrapper.get('select[aria-label="自动刷新间隔"]').setValue('60000')
    expect((wrapper.get('select[aria-label="自动刷新间隔"]').element as HTMLSelectElement).value).toBe('60000')
    wrapper.unmount()
  })

  it('contains no controls that write domain or service state', async () => {
    const { wrapper } = await renderAt('/')
    const forbidden = /创建|提交|审核通过|发布|取消执行|重试执行|补发消息|编辑任务/
    for (const button of wrapper.findAll('button')) {
      expect(button.text()).not.toMatch(forbidden)
    }
  })
})
