import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fixtureSnapshot } from '@/data/fixtureSnapshot'
import { useDashboardStore } from './dashboard'
import type { DashboardQueryPort } from '@/data/queryPort'

describe('dashboard store', () => {
  beforeEach(() => setActivePinia(createPinia()))
  afterEach(() => vi.useRealTimers())

  it('loads a snapshot and marks partial source data', async () => {
    const store = useDashboardStore()
    store.setQueryPort({ getSnapshot: async () => fixtureSnapshot })
    await store.load()
    expect(store.state).toBe('ready')
    expect(store.snapshot?.partial).toBe(true)
    expect(store.snapshot?.tasks).toHaveLength(4)
  })

  it('distinguishes a fully observed empty workspace from unavailable sources', async () => {
    const store = useDashboardStore()
    store.setQueryPort({ getSnapshot: async () => ({
      ...fixtureSnapshot,
      mode: 'live',
      sources: [{ id: 'mapping', label: 'Research Mapping', status: 'fresh', observedAt: '2026-10-22T10:00:00Z' }],
      projects: [], tasks: [], wikiDocuments: [], wikiCandidates: [], executions: [], services: [], events: [], partial: false,
    }) })
    await store.load()
    expect(store.state).toBe('empty')
  })

  it('keeps the last good snapshot when refresh fails', async () => {
    const store = useDashboardStore()
    const port: DashboardQueryPort = { getSnapshot: vi.fn().mockResolvedValueOnce(fixtureSnapshot).mockRejectedValueOnce(new Error('network')) }
    store.setQueryPort(port)
    await store.load()
    await store.refresh()
    expect(store.state).toBe('error')
    expect(store.snapshot).toEqual(fixtureSnapshot)
    expect(store.errorMessage).toContain('暂时无法更新')
  })

  it('exposes refresh progress without hiding the last snapshot', async () => {
    const store = useDashboardStore()
    let resolveRefresh!: (snapshot: typeof fixtureSnapshot) => void
    const port: DashboardQueryPort = {
      getSnapshot: vi.fn()
        .mockResolvedValueOnce(fixtureSnapshot)
        .mockImplementationOnce(() => new Promise((resolve) => { resolveRefresh = resolve })),
    }
    store.setQueryPort(port)
    await store.load()
    const refreshPromise = store.refresh()
    expect(store.refreshing).toBe(true)
    expect(store.snapshot).toEqual(fixtureSnapshot)
    resolveRefresh(fixtureSnapshot)
    await refreshPromise
    expect(store.refreshing).toBe(false)
  })

  it('does not overlap polling with an in-flight manual refresh', async () => {
    const store = useDashboardStore()
    let resolveRefresh!: (snapshot: typeof fixtureSnapshot) => void
    const getSnapshot = vi.fn()
      .mockResolvedValueOnce(fixtureSnapshot)
      .mockImplementationOnce(() => new Promise((resolve) => { resolveRefresh = resolve }))
    store.setQueryPort({ getSnapshot })
    await store.load()
    const manualRefresh = store.refresh()
    const automaticRefresh = store.refresh()
    expect(getSnapshot).toHaveBeenCalledTimes(2)
    resolveRefresh(fixtureSnapshot)
    await Promise.all([manualRefresh, automaticRefresh])
  })

  it('supports controllable polling and stops the timer', async () => {
    vi.useFakeTimers()
    const store = useDashboardStore()
    const getSnapshot = vi.fn().mockResolvedValue(fixtureSnapshot)
    store.setQueryPort({ getSnapshot })
    store.startPolling(1_000)
    await vi.advanceTimersByTimeAsync(1_000)
    expect(getSnapshot).toHaveBeenCalledTimes(1)
    store.stopPolling()
    await vi.advanceTimersByTimeAsync(2_000)
    expect(getSnapshot).toHaveBeenCalledTimes(1)
  })
})
