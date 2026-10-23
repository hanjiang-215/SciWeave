import type { DashboardSnapshot } from '@/domain/dashboard'

export const fixtureSnapshot: DashboardSnapshot = {
  mode: 'fixture',
  observedAt: '2026-10-22T10:00:00Z',
  sources: [
    { id: 'mapping', label: 'Research Mapping', status: 'fresh', observedAt: '2026-10-22T10:00:00Z' },
    { id: 'wiki', label: 'LLM-Wiki', status: 'partial', observedAt: '2026-10-22T09:58:00Z', error: '资源资格查询暂时不可用' },
    { id: 'gateway', label: 'Gateway', status: 'fresh', observedAt: '2026-10-22T10:00:00Z' },
    { id: 'queue', label: '消息监听', status: 'stale', observedAt: '2026-10-22T09:31:00Z', error: '最近一次检查超过新鲜度窗口' },
  ],
  projects: [{ id: 'project-catalyst', name: '催化剂筛选路线', routeId: 'route-catalyst', completed: 2, total: 6, attentionCount: 3 }],
  tasks: [
    { id: 'task-data', projectId: 'project-catalyst', name: '准备实验数据', status: 'succeeded', owner: '研究员 A', prerequisiteIds: [], updatedAt: '2026-10-22T08:10:00Z', attentionRank: 0 },
    { id: 'task-model', projectId: 'project-catalyst', name: '训练初始模型', status: 'waiting', owner: '研究员 B', prerequisiteIds: ['task-data'], blockingReason: '等待 Project Owner 审核候选变化', updatedAt: '2026-10-22T09:30:00Z', attentionRank: 2 },
    { id: 'task-validation', projectId: 'project-catalyst', name: '验证模型', status: 'result_unknown', owner: '研究员 C', prerequisiteIds: ['task-model'], blockingReason: '需要核对远端执行是否已写入正式结果', updatedAt: '2026-10-22T09:40:00Z', attentionRank: 1 },
    { id: 'task-report', projectId: 'project-catalyst', name: '整理验证报告', status: 'queued', owner: '研究员 C', prerequisiteIds: ['task-validation'], updatedAt: '2026-10-22T09:45:00Z', attentionRank: 0 },
  ],
  wikiDocuments: [
    { id: 'wiki-doc-1', title: '催化剂筛选实验设计', domainId: 'wiki-catalyst', formalRevisionId: 'wiki-rev-18', summary: '当前正式版本，引用已确认的实验资源。', updatedAt: '2026-10-22T08:45:00Z', references: [{ id: 'ref-1', resourceVersionId: 'rv-2026-040', qualification: 'approved', requestedScope: '实验条件' }] },
  ],
  wikiCandidates: [
    { id: 'wiki-candidate-1', title: '候选：新增对照实验解释', proposalId: 'proposal-72', state: 'review_pending', updatedAt: '2026-10-22T09:20:00Z', references: [{ id: 'ref-2', resourceVersionId: 'rv-2026-041', qualification: 'pending', requestedScope: '对照实验' }] },
  ],
  executions: [
    { id: 'exec-42', taskId: 'task-validation', status: 'result_unknown', trigger: 'queue', updatedAt: '2026-10-22T09:40:00Z', summary: '消息已接收，但执行结果确认超时', failure: { target: 'task-agent-gateway', tool: 'query_execution', occurredAt: '2026-10-22T09:40:00Z', summary: '远端结果未知，请使用原执行标识对账', idempotencyKey: 'exec-42', executionId: 'exec-42' } },
    { id: 'exec-41', taskId: 'task-model', status: 'waiting', trigger: 'operator', updatedAt: '2026-10-22T09:30:00Z', summary: '等待人工审核候选变化' },
  ],
  services: [
    { id: 'task-listener', name: 'Task Agent 消息监听', role: 'task-agent', status: 'online', lastCheckAt: '2026-10-22T09:59:00Z', subscription: 'TaskNode 交接事件', consumerGroup: 'task-agent-researcher-a' },
    { id: 'centre-listener', name: 'Centre Agent 消息监听', role: 'centre-agent', status: 'stale', lastCheckAt: '2026-10-22T09:31:00Z', subscription: '候选变化事件', consumerGroup: 'centre-agent-review', error: '最近一次状态检查已过期' },
  ],
  events: [
    { id: 'event-1', type: 'formal_release', title: '实验数据正式版本已发布', occurredAt: '2026-10-22T08:10:00Z', taskId: 'task-data' },
    { id: 'event-2', type: 'message_received', title: 'Task Agent 收到交接消息', occurredAt: '2026-10-22T09:25:00Z', taskId: 'task-model' },
    { id: 'event-3', type: 'message_received', title: '重复交接消息已被幂等处理', occurredAt: '2026-10-22T09:26:00Z', taskId: 'task-model', duplicate: true, diagnostic: 'message-key: task-model:release:4' },
    { id: 'event-4', type: 'mcp_failure', title: 'Gateway 查询结果未知', occurredAt: '2026-10-22T09:40:00Z', taskId: 'task-validation', diagnostic: 'execution: exec-42' },
  ],
  partial: true,
}
