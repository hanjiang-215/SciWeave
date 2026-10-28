import { describe, expect, it, vi } from 'vitest'
import { createHttpQuery, DashboardQueryError } from './httpQuery'
import { fixtureSnapshot } from './fixtureSnapshot'

describe('dashboard HTTP query', () => {
  it('requests the snapshot with GET and returns the validated response', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify(fixtureSnapshot), { status: 200 }))
    const query = createHttpQuery('https://example.invalid/dashboard', fetcher)
    const result = await query.getSnapshot()
    const [requestUrl, requestOptions] = fetcher.mock.calls[0]!
    expect(String(requestUrl)).toBe('https://example.invalid/dashboard/api/dashboard/snapshot')
    expect(requestOptions?.method).toBe('GET')
    expect(requestOptions?.headers).toEqual({ Accept: 'application/json' })
    expect(result).toEqual(fixtureSnapshot)
  })

  it('hides upstream error details from the browser', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response('secret token and stack trace', { status: 500 }))
    const query = createHttpQuery('https://example.invalid', fetcher)
    await expect(query.getSnapshot()).rejects.toThrow('数据服务暂时无法更新')
    await expect(query.getSnapshot()).rejects.not.toThrow('secret token')
  })

  it('rejects a task with an unknown state instead of rendering an unclassified badge', async () => {
    const payload = { ...fixtureSnapshot, tasks: [{ ...fixtureSnapshot.tasks[0], status: 'surprise' }] }
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify(payload), { status: 200 }))
    const query = createHttpQuery('https://example.invalid', fetcher)
    await expect(query.getSnapshot()).rejects.toThrow('返回格式不完整')
  })

  it('does not expose access-control response details', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response('private gateway message', { status: 403 }))
    const query = createHttpQuery('https://example.invalid', fetcher)
    await expect(query.getSnapshot()).rejects.toThrow('数据服务暂时无法更新')
    await expect(query.getSnapshot()).rejects.not.toThrow('private gateway message')
  })

  it('rejects a task missing attentionRank so attention items are not silently dropped', async () => {
    const task: Record<string, unknown> = { ...fixtureSnapshot.tasks[0] }
    delete task.attentionRank
    const payload = { ...fixtureSnapshot, tasks: [task] }
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify(payload), { status: 200 }))
    const query = createHttpQuery('https://example.invalid', fetcher)
    await expect(query.getSnapshot()).rejects.toThrow('返回格式不完整')
  })

  it('rejects an execution whose failure fact is missing required fields', async () => {
    const execution: Record<string, unknown> = { ...fixtureSnapshot.executions[0], failure: { target: 'gw', occurredAt: '2026-10-22T09:40:00Z' } }
    const payload = { ...fixtureSnapshot, executions: [execution] }
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify(payload), { status: 200 }))
    const query = createHttpQuery('https://example.invalid', fetcher)
    await expect(query.getSnapshot()).rejects.toThrow('返回格式不完整')
  })

  it('accepts an execution without a failure fact', async () => {
    const execution = { ...fixtureSnapshot.executions[1] }
    const payload = { ...fixtureSnapshot, executions: [execution] }
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify(payload), { status: 200 }))
    const query = createHttpQuery('https://example.invalid', fetcher)
    await expect(query.getSnapshot()).resolves.toBeTruthy()
  })

  it('rejects malformed snapshots instead of showing empty data', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ projects: [], tasks: [] }), { status: 200 }))
    const query = createHttpQuery('https://example.invalid', fetcher)
    const result = query.getSnapshot()
    await expect(result).rejects.toBeInstanceOf(DashboardQueryError)
    await expect(result).rejects.toThrow('返回格式不完整')
  })
})
