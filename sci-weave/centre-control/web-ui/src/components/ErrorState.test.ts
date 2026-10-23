import { createPinia, setActivePinia } from 'pinia'
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ErrorState from './ErrorState.vue'

describe('ErrorState', () => {
  it('disables its retry action while refreshing', () => {
    const wrapper = mount(ErrorState, { props: { message: '当前数据已保留。', busy: true } })
    expect(wrapper.get('button').text()).toBe('正在刷新…')
    expect(wrapper.get('button').attributes('disabled')).toBeDefined()
  })
})
