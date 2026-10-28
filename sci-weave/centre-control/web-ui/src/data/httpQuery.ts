import type { DashboardSnapshot } from '@/domain/dashboard'
import type { DashboardQueryPort } from './queryPort'

export class DashboardQueryError extends Error {
  readonly statusCode?: number

  constructor(message: string, statusCode?: number) {
    super(message)
    this.name = 'DashboardQueryError'
    this.statusCode = statusCode
  }
}

export function createHttpQuery(baseUrl: string, fetcher: typeof fetch = fetch): DashboardQueryPort {
  return {
    async getSnapshot(signal) {
      let response: Response
      try {
        response = await fetcher(new URL('api/dashboard/snapshot', ensureTrailingSlash(baseUrl)), {
          method: 'GET',
          headers: { Accept: 'application/json' },
          signal,
        })
      } catch {
        throw new DashboardQueryError('数据服务暂时无法连接，请稍后重试。')
      }
      if (!response.ok) {
        throw new DashboardQueryError('数据服务暂时无法更新，请保留当前数据并稍后重试。', response.status)
      }
      let payload: unknown
      try {
        payload = await response.json()
      } catch {
        throw new DashboardQueryError('数据服务返回内容无法读取，请联系平台维护人员。', response.status)
      }
      if (!isDashboardSnapshot(payload)) {
        throw new DashboardQueryError('数据服务返回格式不完整，请联系平台维护人员。', response.status)
      }
      return payload
    },
  }
}

function ensureTrailingSlash(value: string): string {
  return value.endsWith('/') ? value : `${value}/`
}

function isDashboardSnapshot(value: unknown): value is DashboardSnapshot {
  if (!isRecord(value)) return false
  return isString(value.mode)
    && (value.mode === 'fixture' || value.mode === 'live')
    && isString(value.observedAt)
    && Array.isArray(value.sources) && value.sources.every(isDataSource)
    && Array.isArray(value.projects) && value.projects.every(isProject)
    && Array.isArray(value.tasks) && value.tasks.every(isTask)
    && Array.isArray(value.wikiDocuments) && value.wikiDocuments.every(isWikiDocument)
    && Array.isArray(value.wikiCandidates) && value.wikiCandidates.every(isWikiCandidate)
    && Array.isArray(value.executions) && value.executions.every(isExecution)
    && Array.isArray(value.services) && value.services.every(isService)
    && Array.isArray(value.events) && value.events.every(isEvent)
    && typeof value.partial === 'boolean'
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}
function isString(value: unknown): value is string { return typeof value === 'string' }
function isStringArray(value: unknown): value is string[] { return Array.isArray(value) && value.every(isString) }
function isReference(value: unknown): boolean {
  return isRecord(value) && isString(value.id) && isString(value.resourceVersionId)
    && ['approved', 'pending', 'rejected', 'revoked', 'unknown'].includes(String(value.qualification))
    && isString(value.requestedScope)
}
function isDataSource(value: unknown): boolean {
  return isRecord(value) && isString(value.id) && isString(value.label)
    && ['fresh', 'stale', 'unavailable', 'partial'].includes(String(value.status))
}
function isProject(value: unknown): boolean {
  return isRecord(value) && isString(value.id) && isString(value.name) && isString(value.routeId)
    && Number.isFinite(value.completed) && Number.isFinite(value.total) && Number.isFinite(value.attentionCount)
}
function isTask(value: unknown): boolean {
  return isRecord(value) && isString(value.id) && isString(value.projectId) && isString(value.name)
    && ['queued', 'running', 'waiting', 'succeeded', 'revision_required', 'cancelled', 'failed', 'result_unknown', 'unknown'].includes(String(value.status))
    && isString(value.owner) && isStringArray(value.prerequisiteIds) && Number.isFinite(value.attentionRank)
    && isString(value.updatedAt)
}
function isWikiDocument(value: unknown): boolean {
  return isRecord(value) && isString(value.id) && isString(value.title) && isString(value.domainId)
    && isString(value.formalRevisionId) && isString(value.summary) && isString(value.updatedAt)
    && Array.isArray(value.references) && value.references.every(isReference)
}
function isWikiCandidate(value: unknown): boolean {
  return isRecord(value) && isString(value.id) && isString(value.title) && isString(value.proposalId)
    && ['candidate', 'review_pending', 'approved_pending_formalization', 'rejected', 'revoked', 'formalized'].includes(String(value.state))
    && isString(value.updatedAt) && Array.isArray(value.references) && value.references.every(isReference)
}
function isExecution(value: unknown): boolean {
  return isRecord(value) && isString(value.id) && isString(value.taskId)
    && ['queued', 'running', 'waiting', 'succeeded', 'cancelled', 'failed', 'result_unknown', 'completed', 'needs_revision', 'rejected', 'human_takeover'].includes(String(value.status))
    && ['queue', 'operator'].includes(String(value.trigger)) && isString(value.updatedAt)
}
function isService(value: unknown): boolean {
  return isRecord(value) && isString(value.id) && isString(value.name)
    && ['task-agent', 'centre-agent'].includes(String(value.role))
    && ['online', 'stale', 'unavailable', 'unknown'].includes(String(value.status))
}
function isEvent(value: unknown): boolean {
  return isRecord(value) && isString(value.id) && isString(value.title) && isString(value.occurredAt)
    && ['formal_release', 'candidate_change', 'message_received', 'execution_completed', 'mcp_failure'].includes(String(value.type))
}
