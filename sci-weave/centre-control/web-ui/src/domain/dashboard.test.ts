import {
  attentionItems,
  filterTasks,
  formatInstant,
  sourceLabel,
  type DashboardSnapshot,
  type TaskNode,
} from './dashboard'

const snapshot: DashboardSnapshot = {
  mode: 'live',
  observedAt: '2026-10-22T10:00:00Z',
  sources: [
    { id: 'mapping', label: 'Research Mapping', status: 'fresh', observedAt: '2026-10-22T10:00:00Z' },
  ],
  projects: [{ id: 'p1', name: '催化剂筛选', routeId: 'route-1', completed: 1, total: 4, attentionCount: 3 }],
  tasks: [
    { id: 'task-1', projectId: 'p1', name: '准备数据', status: 'succeeded', owner: '研究员 A', prerequisiteIds: [], attentionRank: 0, updatedAt: '2026-10-22T09:00:00Z' },
    { id: 'task-2', projectId: 'p1', name: '训练初始模型', status: 'waiting', owner: '研究员 B', prerequisiteIds: ['task-1'], blockingReason: '等待 Project Owner 审核', attentionRank: 2, updatedAt: '2026-10-22T09:30:00Z' },
    { id: 'task-3', projectId: 'p1', name: '验证模型', status: 'result_unknown', owner: '研究员 C', prerequisiteIds: ['task-2'], attentionRank: 1, updatedAt: '2026-10-22T09:40:00Z' },
  ],
  wikiDocuments: [],
  wikiCandidates: [],
  executions: [],
  services: [],
  events: [],
  partial: false,
}

describe('dashboard domain', () => {
  it('sorts attention items by rank and keeps task context', () => {
    expect(attentionItems(snapshot).map((item) => item.id)).toEqual(['task-3', 'task-2'])
    expect(attentionItems(snapshot)[1]?.reason).toBe('等待 Project Owner 审核')
  })

  it('filters tasks by status and search text', () => {
    expect(filterTasks(snapshot.tasks, { status: 'waiting', query: '' })).toHaveLength(1)
    expect(filterTasks(snapshot.tasks, { status: 'all', query: '模型' }).map((task) => task.id)).toEqual(['task-2', 'task-3'])
  })

  it('describes source freshness without relying on color', () => {
    expect(sourceLabel({ status: 'stale' })).toEqual('数据可能过期')
    expect(sourceLabel({ status: 'unavailable' })).toEqual('数据暂不可用')
    expect(sourceLabel({ status: 'partial' })).toEqual('部分数据')
  })
})

describe('formatInstant', () => {
  it('renders a valid timestamp and never throws on garbage', () => {
    expect(formatInstant('2026-10-22T09:00:00Z')).toBeTruthy()
    // The old code called Intl.format(new Date('nope')) and threw RangeError,
    // aborting the whole render for one bad row.
    expect(() => formatInstant('not-a-date')).not.toThrow()
    expect(formatInstant('not-a-date')).toBe('时间未知')
    expect(formatInstant(undefined)).toBe('—')
  })
})

describe('attentionItems ordering across time zones', () => {
  it('orders by instant, not by the raw string', () => {
    const make = (id: string, updatedAt: string): TaskNode => ({
      id, projectId: 'p1', name: id, status: 'waiting', owner: 'o',
      prerequisiteIds: [], attentionRank: 1, updatedAt,
    })
    const withTasks = (tasks: TaskNode[]): DashboardSnapshot => ({ ...snapshot, tasks })
    // 02:30Z is 10:30+08:00 -- newer in real time but sorts BEFORE +08:00 as text.
    const ordered = attentionItems(
      withTasks([make('task-early', '2026-10-22T10:00:00+08:00'), make('task-late', '2026-10-22T02:30:00Z')]),
    )
    expect(ordered.map((item) => item.id)).toEqual(['task-late', 'task-early'])
  })
})
