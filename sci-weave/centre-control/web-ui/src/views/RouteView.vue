<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import StatusBadge from '@/components/StatusBadge.vue'
import EmptyState from '@/components/EmptyState.vue'
import TaskMap from '@/components/TaskMap.vue'
import { taskStatusLabel, type TaskStatus } from '@/domain/dashboard'
import { useDashboardStore } from '@/stores/dashboard'

const store = useDashboardStore()
const route = useRoute()
const router = useRouter()
const statusOptions: Array<{ value: TaskStatus | 'all'; label: string }> = [
  { value: 'all', label: '全部状态' }, { value: 'queued', label: '等待执行' }, { value: 'running', label: '执行中' },
  { value: 'waiting', label: '等待处理' }, { value: 'succeeded', label: '已完成' }, { value: 'revision_required', label: '需要返修' },
  { value: 'failed', label: '已确认失败' }, { value: 'result_unknown', label: '结果未知' }, { value: 'unknown', label: '状态未知' },
]
const validStatuses = new Set(statusOptions.map((option) => option.value))
const project = computed(() => store.snapshot?.projects[0])
const tasks = computed(() => store.filteredTasks)
// 'map' is the default because the dependency graph is the primary way to read
// how work fans out; 'list' keeps the original scannable card column.
const viewMode = ref<'map' | 'list'>('map')

// Two watchers that each feed the other: route -> store, and store -> route.
// Without suppressing re-entry they can ping-pong, and each hop issues a
// router.replace. Guard both directions so a change that a watcher itself caused
// does not immediately re-trigger the opposite one.
let syncingFromRoute = false
let syncingToRoute = false

function applyRouteFilters(): void {
  if (syncingToRoute) return
  syncingFromRoute = true
  const rawStatus = typeof route.query.status === 'string' ? route.query.status : 'all'
  store.setFilters({ status: validStatuses.has(rawStatus as TaskStatus) ? rawStatus as TaskStatus : 'all', query: typeof route.query.q === 'string' ? route.query.q : '' })
  syncingFromRoute = false
}

function updateQuery(): void {
  if (syncingFromRoute) return
  const query = { ...route.query, status: store.statusFilter === 'all' ? undefined : store.statusFilter, q: store.searchQuery.trim() || undefined }
  syncingToRoute = true
  void Promise.resolve(router.replace({ query })).finally(() => {
    syncingToRoute = false
  })
}

watch(() => [route.query.status, route.query.q], applyRouteFilters, { immediate: true })
watch(() => [store.statusFilter, store.searchQuery], updateQuery)

function taskName(id: string): string {
  return store.snapshot?.tasks.find((task) => task.id === id)?.name ?? id
}
</script>

<template>
  <div class="page-stack">
    <header class="page-header"><div><p class="eyebrow">研究路径 · RESEARCH MAPPING</p><h1>路线与任务</h1><p>从依赖关系理解每项工作的进度、等待原因和后续关联。</p></div><div v-if="project" class="route-total"><strong>{{ project.completed }}<span>/</span>{{ project.total }}</strong><small>已完成任务</small></div></header>
    <section class="filter-panel" aria-label="任务筛选"><label class="search-field"><span aria-hidden="true">⌕</span><input v-model="store.searchQuery" type="search" placeholder="搜索任务、负责人或等待原因" aria-label="搜索任务、负责人或等待原因" /></label><label class="status-select"><span>状态</span><select :value="store.statusFilter" aria-label="按状态筛选任务" @change="store.setFilters({ status: ($event.target as HTMLSelectElement).value as TaskStatus | 'all' })"><option v-for="option in statusOptions" :key="option.value" :value="option.value">{{ option.label }}</option></select></label><button v-if="store.statusFilter !== 'all' || store.searchQuery" class="clear-filter" type="button" @click="store.resetFilters(); updateQuery()">清除筛选</button></section>
    <div v-if="tasks.length" class="view-switch" role="tablist" aria-label="切换任务视图">
      <button type="button" role="tab" :aria-selected="viewMode === 'map'" :class="{ 'view-switch__tab--active': viewMode === 'map' }" class="view-switch__tab" @click="viewMode = 'map'"><span aria-hidden="true">⋔</span> 思维导图</button>
      <button type="button" role="tab" :aria-selected="viewMode === 'list'" :class="{ 'view-switch__tab--active': viewMode === 'list' }" class="view-switch__tab" @click="viewMode = 'list'"><span aria-hidden="true">☰</span> 列表</button>
    </div>
    <TaskMap v-if="tasks.length && viewMode === 'map'" :tasks="tasks" />
    <section v-else-if="tasks.length" class="task-board" aria-label="TaskNode 列表">
      <article v-for="(task, index) in tasks" :key="task.id" class="task-card">
        <div class="task-card__rail"><span class="task-card__number">{{ String(index + 1).padStart(2, '0') }}</span><span class="task-card__connector" aria-hidden="true"></span></div>
        <div class="task-card__main"><div class="task-card__heading"><div><p class="eyebrow">TASK NODE · {{ task.logicalId ?? task.id }}</p><h2><RouterLink :to="`/tasks/${task.id}`">{{ task.name }}</RouterLink></h2></div><StatusBadge :status="task.status" /></div><p v-if="task.blockingReason" class="blocker-note"><span aria-hidden="true">↳</span><span>{{ task.blockingReason }}</span></p><p v-else class="task-context">由 {{ task.owner }} 负责跟进 · {{ taskStatusLabel(task.status) }}</p><div class="dependency-row"><strong>前置任务</strong><span v-if="task.prerequisiteIds.length" class="dependency-links"><RouterLink v-for="id in task.prerequisiteIds" :key="id" :to="`/tasks/${id}`">{{ taskName(id) }} <span aria-hidden="true">↗</span></RouterLink></span><span v-else class="no-prerequisites">无前置任务 · 可独立启动</span></div></div><RouterLink class="task-card__open" :to="`/tasks/${task.id}`" :aria-label="`查看${task.name}详情`">↗</RouterLink>
      </article>
    </section>
    <EmptyState v-else title="没有匹配的任务" description="调整状态筛选或搜索词，查看其他研究节点。" />
    <p v-if="store.snapshot?.partial" class="route-note" role="status">当前路线数据包含部分来源结果。请以各数据源的观测时间和状态为准。</p>
  </div>
</template>

<style scoped>
.view-switch{display:inline-flex;gap:.2rem;align-self:flex-start;padding:.22rem;border:1px solid #e5e7e0;border-radius:.7rem;background:#f3f5f0}.view-switch__tab{display:inline-flex;align-items:center;gap:.38rem;border:0;border-radius:.52rem;padding:.4rem .8rem;background:transparent;color:#74827a;font:inherit;font-size:.76rem;font-weight:700;cursor:pointer;transition:background .16s,color .16s}.view-switch__tab:hover{color:#415247}.view-switch__tab--active{background:#fffefa;color:#26543f;box-shadow:0 1px 2px rgba(27,40,34,.08)}.view-switch__tab:focus-visible{outline:3px solid #d77a3b;outline-offset:1px}
.page-stack{display:grid;gap:1rem}.page-header{display:flex;align-items:flex-end;justify-content:space-between;gap:1rem;padding:.4rem 0 .6rem}.page-header h1{margin:0;color:#1b2822;font-family:Georgia,'Noto Serif SC',serif;font-size:2.35rem;font-weight:500;letter-spacing:-.06em}.page-header>div:first-child>p:last-child{margin:.55rem 0 0;color:#718078;font-size:.88rem}.route-total{display:grid;gap:.1rem;padding:0 0 .25rem 1.2rem;border-left:1px solid #cfd8d1}.route-total strong{color:#26382e;font-family:Georgia,serif;font-size:1.65rem;font-weight:500}.route-total strong span{padding:0 .25rem;color:#9ba69f;font-size:1rem}.route-total small{color:#849087;font-size:.7rem}.filter-panel{display:flex;align-items:center;gap:.7rem;padding:.7rem;border:1px solid #e5e7e0;border-radius:.9rem;background:#fffefa}.search-field{display:flex;align-items:center;gap:.55rem;flex:1;min-width:10rem;padding:0 .55rem;color:#87938b}.search-field span{font-size:1.2rem}.search-field input{width:100%;border:0;outline:none;background:transparent;color:#27352e;font:inherit;font-size:.83rem}.search-field input::placeholder{color:#a5aca7}.status-select{display:flex;align-items:center;gap:.4rem;padding:0 .55rem;border-left:1px solid #e7e8e2;color:#859088;font-size:.74rem}.status-select select{border:0;background:transparent;color:#344139;font:inherit;font-weight:650;outline-offset:3px}.clear-filter{border:0;background:transparent;color:#407260;font:inherit;font-size:.75rem;font-weight:700;cursor:pointer}.task-board{display:grid;gap:.7rem}.task-card{display:grid;grid-template-columns:2.2rem minmax(0,1fr) 2.2rem;gap:.4rem;padding:1rem 1.1rem;border:1px solid #e6e7e0;border-radius:.95rem;background:#fffefa;transition:border-color .16s,transform .16s}.task-card:hover{transform:translateY(-1px);border-color:#b8c9bd}.task-card__rail{display:flex;align-items:center;flex-direction:column;gap:.5rem}.task-card__number{color:#9ba59d;font-family:Georgia,serif;font-size:.78rem}.task-card__connector{width:1px;flex:1;min-height:2rem;background:linear-gradient(#d8e1da,transparent)}.task-card:last-child .task-card__connector{display:none}.task-card__main{min-width:0}.task-card__heading{display:flex;align-items:flex-start;justify-content:space-between;gap:1rem}.task-card__heading h2{margin:0;color:#24332b;font-size:1.05rem;font-weight:680}.task-card__heading h2 a{color:inherit;text-decoration:none}.task-card__heading h2 a:focus-visible,.dependency-links a:focus-visible{outline:2px solid #d77a3b;outline-offset:3px}.task-card__heading .eyebrow{font-size:.59rem}.blocker-note{display:flex;align-items:flex-start;gap:.4rem;margin:.65rem 0;color:#9a5d20;font-size:.78rem;line-height:1.5}.task-context{margin:.65rem 0;color:#7a857d;font-size:.77rem}.dependency-row{display:flex;flex-wrap:wrap;align-items:baseline;gap:.55rem;margin-top:.8rem;padding-top:.65rem;border-top:1px solid #eff0eb}.dependency-row strong{color:#919b93;font-size:.67rem;font-weight:700}.dependency-links{display:flex;flex-wrap:wrap;gap:.4rem}.dependency-links a{padding:.25rem .5rem;border-radius:.35rem;background:#f0f4ef;color:#527260;text-decoration:none;font-size:.69rem}.no-prerequisites{color:#7a8980;font-size:.69rem}.task-card__open{align-self:center;display:grid;place-items:center;width:2rem;height:2rem;border:1px solid #dce4de;border-radius:50%;color:#648472;text-decoration:none}.task-card__open:focus-visible{outline:3px solid #d77a3b}.route-note{margin:0;padding:.75rem 1rem;border-radius:.7rem;background:#fff4df;color:#80561f;font-size:.77rem}
@media(max-width:600px){.page-header{align-items:flex-start}.page-header h1{font-size:1.9rem}.route-total{padding-left:.7rem}.filter-panel{flex-wrap:wrap}.search-field{flex-basis:100%;padding:.35rem .5rem}.status-select{border-left:0;padding-left:.5rem}.task-card{grid-template-columns:1.5rem minmax(0,1fr) 1.7rem;padding:.8rem}.task-card__heading{flex-direction:column;gap:.55rem}.task-card__heading h2{font-size:.95rem}.task-card__heading .eyebrow{overflow-wrap:anywhere}}
</style>
