export type SnapshotStatus = 'fresh' | 'stale' | 'unavailable' | 'partial'
export type TaskStatus = 'queued' | 'running' | 'waiting' | 'succeeded' | 'revision_required' | 'cancelled' | 'failed' | 'result_unknown' | 'unknown'
export type ExecutionStatus = Exclude<TaskStatus, 'revision_required'> | 'completed' | 'needs_revision' | 'rejected' | 'human_takeover'

export interface DataSource {
  id: string
  label: string
  status: SnapshotStatus
  observedAt?: string
  freshUntil?: string
  error?: string
}

export interface ProjectSummary {
  id: string
  name: string
  routeId: string
  completed: number
  total: number
  attentionCount: number
}

export interface TaskNode {
  id: string
  logicalId?: string
  projectId: string
  name: string
  status: TaskStatus
  owner: string
  prerequisiteIds: string[]
  blockingReason?: string
  updatedAt: string
  attentionRank: number
}

export interface ExecutionRecord {
  id: string
  taskId: string
  status: ExecutionStatus
  trigger: 'queue' | 'operator'
  updatedAt: string
  summary?: string
  failure?: FailureFact
}

export interface FailureFact {
  target: string
  tool?: string
  occurredAt: string
  summary: string
  idempotencyKey?: string
  executionId?: string
}

export interface ServiceStatus {
  id: string
  name: string
  role: 'task-agent' | 'centre-agent'
  status: 'online' | 'stale' | 'unavailable' | 'unknown'
  lastCheckAt?: string
  subscription?: string
  consumerGroup?: string
  error?: string
}

export interface ActivityEvent {
  id: string
  type: 'formal_release' | 'candidate_change' | 'message_received' | 'execution_completed' | 'mcp_failure'
  title: string
  occurredAt: string
  taskId?: string
  duplicate?: boolean
  diagnostic?: string
}

export interface WikiReferenceSummary {
  id: string
  resourceVersionId: string
  qualification: 'approved' | 'pending' | 'rejected' | 'revoked' | 'unknown'
  requestedScope: string
  limitations?: string[]
}

export interface WikiFormalDocumentSummary {
  id: string
  title: string
  domainId: string
  formalRevisionId: string
  summary: string
  updatedAt: string
  references: WikiReferenceSummary[]
}

export interface WikiCandidateSummary {
  id: string
  title: string
  proposalId: string
  state: 'candidate' | 'review_pending' | 'approved_pending_formalization' | 'rejected' | 'revoked' | 'formalized'
  candidateSnapshotStatus?: 'confirmed' | 'unavailable' | 'pending'
  updatedAt: string
  references: WikiReferenceSummary[]
}

export interface DashboardSnapshot {
  mode: 'fixture' | 'live'
  observedAt: string
  sources: DataSource[]
  projects: ProjectSummary[]
  tasks: TaskNode[]
  wikiDocuments: WikiFormalDocumentSummary[]
  wikiCandidates: WikiCandidateSummary[]
  executions: ExecutionRecord[]
  services: ServiceStatus[]
  events: ActivityEvent[]
  partial: boolean
}

export interface TaskFilter {
  status: TaskStatus | 'all'
  query: string
}

export interface AttentionItem {
  id: string
  title: string
  status: TaskStatus
  reason: string
  updatedAt: string
}

export function filterTasks(tasks: TaskNode[], filter: TaskFilter): TaskNode[] {
  const query = filter.query.trim().toLocaleLowerCase()
  return tasks.filter((task) => {
    const matchesStatus = filter.status === 'all' || task.status === filter.status
    const matchesQuery = !query || `${task.name} ${task.owner} ${task.blockingReason ?? ''}`.toLocaleLowerCase().includes(query)
    return matchesStatus && matchesQuery
  })
}

export function attentionItems(snapshot: DashboardSnapshot): AttentionItem[] {
  return snapshot.tasks
    .filter((task) => task.attentionRank > 0)
    // Compare parsed instants, not the raw ISO strings: a plain string compare is
    // wrong as soon as two rows use different offsets (e.g. +08:00 vs Z), and an
    // unparseable timestamp must sort to the end rather than crash the sort.
    .sort(
      (left, right) =>
        left.attentionRank - right.attentionRank || compareInstantsDesc(left.updatedAt, right.updatedAt),
    )
    .map((task) => ({
      id: task.id,
      title: task.name,
      status: task.status,
      reason: task.blockingReason ?? statusDescription(task.status),
      updatedAt: task.updatedAt,
    }))
}

function instantOf(value: string): number {
  const parsed = Date.parse(value)
  return Number.isNaN(parsed) ? Number.NEGATIVE_INFINITY : parsed
}

/** Newest first; entries with an invalid time fall to the bottom. */
function compareInstantsDesc(left: string, right: string): number {
  return instantOf(right) - instantOf(left)
}

const TIME_ZONE = 'Asia/Shanghai'
const timeOnlyFormat = new Intl.DateTimeFormat('zh-CN', { hour: '2-digit', minute: '2-digit', timeZone: TIME_ZONE })
const shortFormat = new Intl.DateTimeFormat('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: TIME_ZONE })
const mediumFormat = new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short', timeZone: TIME_ZONE })

/**
 * Format an ISO timestamp, tolerating bad input.
 *
 * ``new Date('garbage')`` is an Invalid Date and ``Intl.DateTimeFormat.format``
 * throws ``RangeError`` on it, which used to abort the whole render for one
 * malformed row. Return a neutral placeholder instead so the rest still shows.
 */
export function formatInstant(value: string | undefined, style: 'time' | 'short' | 'medium' = 'short'): string {
  if (!value) return '—'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return '时间未知'
  const formatter = style === 'time' ? timeOnlyFormat : style === 'medium' ? mediumFormat : shortFormat
  return formatter.format(parsed)
}

export function statusDescription(status: TaskStatus | ExecutionStatus): string {
  const descriptions: Record<string, string> = {
    queued: '等待执行', running: '执行中', waiting: '等待处理', succeeded: '已完成', completed: '已完成',
    revision_required: '需要返修', needs_revision: '需要返修', cancelled: '已取消', rejected: '已拒绝',
    human_takeover: '已转人工', failed: '已确认失败', result_unknown: '结果未知',
  }
  return descriptions[status] ?? '状态未知'
}

export function sourceLabel(source: Pick<DataSource, 'status'>): string {
  return { fresh: '数据最新', stale: '数据可能过期', unavailable: '数据暂不可用', partial: '部分数据' }[source.status]
}

export function taskStatusLabel(status: TaskStatus): string {
  return statusDescription(status)
}
