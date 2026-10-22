import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import StatusBadge from './StatusBadge.vue'

describe('StatusBadge', () => {
  it('renders a visible and accessible label for a result-unknown state', () => {
    const wrapper = mount(StatusBadge, { props: { status: 'result_unknown' } })
    expect(wrapper.text()).toContain('结果未知')
    expect(wrapper.attributes('aria-label')).toBe('状态：结果未知')
  })

  it('does not rely on color alone for failure states', () => {
    const wrapper = mount(StatusBadge, { props: { status: 'failed' } })
    expect(wrapper.element.tagName).toBe('SPAN')
    expect(wrapper.text()).toBe('已确认失败')
  })

  it('updates the label when refreshed data changes the status', async () => {
    const wrapper = mount(StatusBadge, { props: { status: 'waiting' } })
    await wrapper.setProps({ status: 'succeeded' })
    expect(wrapper.text()).toBe('已完成')
    expect(wrapper.attributes('aria-label')).toBe('状态：已完成')
  })
})
