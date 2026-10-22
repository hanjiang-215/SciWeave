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

  it('rejects malformed snapshots instead of showing empty data', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ projects: [], tasks: [] }), { status: 200 }))
    const query = createHttpQuery('https://example.invalid', fetcher)
    const result = query.getSnapshot()
    await expect(result).rejects.toBeInstanceOf(DashboardQueryError)
    await expect(result).rejects.toThrow('返回格式不完整')
  })
})
