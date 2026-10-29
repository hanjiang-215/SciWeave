import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { filterTasks, type DashboardSnapshot, type TaskFilter, type TaskStatus } from '@/domain/dashboard'
import { fixtureQuery } from '@/data/fixtureQuery'
import type { DashboardQueryPort } from '@/data/queryPort'

export type DashboardLoadState = 'idle' | 'loading' | 'ready' | 'empty' | 'error'

function isAbortError(error: unknown): boolean {
  return typeof error === 'object' && error !== null && (error as { name?: string }).name === 'AbortError'
}

export const useDashboardStore = defineStore('dashboard', () => {
  const snapshot = ref<DashboardSnapshot | null>(null)
  const state = ref<DashboardLoadState>('idle')
  const errorMessage = ref('')
  const statusFilter = ref<TaskStatus | 'all'>('all')
  const searchQuery = ref('')
  const polling = ref(false)
  const refreshing = ref(false)
  const queryPort = ref<DashboardQueryPort>(fixtureQuery)
  const filteredTasks = computed(() => snapshot.value
    ? filterTasks(snapshot.value.tasks, { status: statusFilter.value, query: searchQuery.value })
    : [])
  let timer: ReturnType<typeof setInterval> | undefined
  let activeController: AbortController | undefined

  function setQueryPort(port: DashboardQueryPort): void {
    queryPort.value = port
  }

  async function load(): Promise<void> {
    if (refreshing.value || state.value === 'loading') return
    state.value = snapshot.value ? state.value : 'loading'
    errorMessage.value = ''
    refreshing.value = true
    activeController?.abort()
    const controller = new AbortController()
    activeController = controller
    try {
      const result = await queryPort.value.getSnapshot(controller.signal)
      snapshot.value = result
      const hasData = [result.projects, result.tasks, result.wikiDocuments, result.wikiCandidates, result.executions, result.services, result.events]
        .some((collection) => collection.length > 0)
      state.value = hasData || result.sources.some((source) => source.status !== 'fresh') ? 'ready' : 'empty'
    } catch (error) {
      // A cancelled request is not a failure: a newer load superseded this one
      // or the view unmounted, so keep the last good snapshot and message
      // instead of telling the user the data is broken (ai4-onvr).
      if (isAbortError(error)) return
      state.value = 'error'
      errorMessage.value = '数据暂时无法更新，已保留最近一次成功读取的内容。请稍后重试。'
    } finally {
      if (activeController === controller) activeController = undefined
      refreshing.value = false
    }
  }

  async function refresh(): Promise<void> {
    if (state.value === 'loading') {
      await load()
      return
    }
    await load()
  }

  function startPolling(intervalMs = 30_000): void {
    stopPolling()
    polling.value = true
    timer = setInterval(() => void refresh(), Math.max(intervalMs, 1_000))
  }

  function stopPolling(): void {
    if (timer) clearInterval(timer)
    timer = undefined
    polling.value = false
  }

  function setFilters(filter: Partial<TaskFilter>): void {
    if (filter.status !== undefined) statusFilter.value = filter.status
    if (filter.query !== undefined) searchQuery.value = filter.query
  }

  function resetFilters(): void {
    statusFilter.value = 'all'
    searchQuery.value = ''
  }

  return {
    snapshot,
    state,
    errorMessage,
    statusFilter,
    searchQuery,
    polling,
    refreshing,
    filteredTasks,
    load,
    refresh,
    startPolling,
    stopPolling,
    setFilters,
    resetFilters,
    setQueryPort,
  }
})
