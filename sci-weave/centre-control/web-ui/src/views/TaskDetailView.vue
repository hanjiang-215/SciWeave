<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import EmptyState from '@/components/EmptyState.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { formatInstant, statusDescription } from '@/domain/dashboard'
import { useDashboardStore } from '@/stores/dashboard'

const route = useRoute()
const store = useDashboardStore()
const task = computed(() => store.snapshot?.tasks.find((item) => item.id === route.params.taskId))
const prerequisites = computed(() => task.value?.prerequisiteIds.map((id) => store.snapshot?.tasks.find((item) => item.id === id)).filter((item) => item !== undefined) ?? [])
const executions = computed(() => store.snapshot?.executions.filter((item) => item.taskId === route.params.taskId) ?? [])
function timeLabel(value: string): string { return formatInstant(value, 'medium') }
</script>

<template>
  <div v-if="task" class="page-stack">
    <nav class="breadcrumbs" aria-label="面包屑"><RouterLink to="/route">研究路线</RouterLink><span aria-hidden="true">/</span><span>{{ task.name }}</span></nav>
    <section class="task-hero"><div><p class="eyebrow">TASK NODE · {{ task.id }}</p><h1>{{ task.name }}</h1><p>负责人：{{ task.owner }} · 最近更新：{{ timeLabel(task.updatedAt) }}</p></div><StatusBadge :status="task.status" /></section>
    <div v-if="task.blockingReason" class="blocker-panel" role="status"><span aria-hidden="true">↳</span><div><strong>当前等待原因</strong><p>{{ task.blockingReason }}</p></div></div>
    <div class="detail-grid"><section class="panel"><header class="section-heading"><div><p class="eyebrow">DEPENDENCIES</p><h2>前置任务</h2></div></header><ul v-if="prerequisites.length" class="related-list"><li v-for="parent in prerequisites" :key="parent.id"><RouterLink :to="`/tasks/${parent.id}`"><span>{{ parent.name }}</span><StatusBadge :status="parent.status" /></RouterLink></li></ul><EmptyState v-else title="没有前置任务" description="此任务在当前路线中不依赖其他已登记节点。" /></section><section class="panel"><header class="section-heading"><div><p class="eyebrow">EXECUTION HISTORY</p><h2>关联执行记录</h2></div></header><ul v-if="executions.length" class="related-list"><li v-for="execution in executions" :key="execution.id"><div class="execution-summary"><strong>{{ execution.id }}</strong><small>{{ execution.trigger === 'queue' ? '由消息触发' : '人工处置后产生' }} · {{ timeLabel(execution.updatedAt) }}</small><p>{{ execution.summary ?? statusDescription(execution.status) }}</p><p v-if="execution.failure" class="failure-detail">{{ execution.failure.summary }}<code v-if="execution.failure.idempotencyKey">核对标识：{{ execution.failure.idempotencyKey }}</code></p></div><StatusBadge :status="execution.status" /></li></ul><EmptyState v-else title="暂无执行记录" description="当前快照中没有与此任务关联的执行记录。" /></section></div>
    <section class="panel identity-panel"><div><p class="eyebrow">正式版本与诊断</p><h2>核对来源，理解当前状态</h2><p>看板只呈现读取到的事实。候选变化、消息接收和执行记录不自动代表正式版本已更新。</p></div><RouterLink to="/operations">查看运行观察 <span aria-hidden="true">↗</span></RouterLink></section>
    <footer class="page-footnote"><RouterLink to="/route">← 返回研究路线</RouterLink><span>只读详情 · 不提供任务编辑或状态修改</span></footer>
  </div>
  <EmptyState v-else title="找不到这个任务" description="任务可能不在当前快照中，或其数据来源暂时不可用。返回路线列表查看当前可用节点。"><template #default><RouterLink to="/route">返回研究路线</RouterLink></template></EmptyState>
</template>

<style scoped>
.page-stack{display:grid;gap:1rem}.breadcrumbs{display:flex;align-items:center;gap:.55rem;color:#929b94;font-size:.74rem}.breadcrumbs a,.page-footnote a{color:#527b65;text-decoration:none}.breadcrumbs span:last-child{overflow:hidden;color:#66746a;text-overflow:ellipsis;white-space:nowrap}.task-hero{display:flex;align-items:center;justify-content:space-between;gap:1rem;padding:1.6rem;border-radius:1rem;background:#dfe9e3}.task-hero h1{margin:0;color:#17251f;font-family:Georgia,'Noto Serif SC',serif;font-size:clamp(1.7rem,4vw,2.5rem);font-weight:500;letter-spacing:-.05em}.task-hero p:last-child{margin:.6rem 0 0;color:#64756a;font-size:.77rem}.task-hero .eyebrow{margin:0 0 .4rem}.blocker-panel{display:flex;gap:.7rem;padding:.9rem 1rem;border:1px solid #efd49f;border-radius:.8rem;background:#fff6e8;color:#855615}.blocker-panel>span{font-size:1.1rem}.blocker-panel strong{font-size:.78rem}.blocker-panel p{margin:.25rem 0 0;color:#846d4b;font-size:.8rem;line-height:1.5}.detail-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1rem}.panel{min-width:0;border:1px solid #e7e6df;border-radius:1rem;background:#fffefa;padding:1.15rem}.section-heading{display:flex;justify-content:space-between;margin-bottom:.9rem}.section-heading .eyebrow{margin-bottom:.2rem}.section-heading h2,.identity-panel h2{margin:0;color:#25342c;font-family:Georgia,'Noto Serif SC',serif;font-size:1.12rem;font-weight:500}.related-list{display:grid;gap:.55rem;list-style:none;margin:0;padding:0}.related-list>li>a{display:flex;align-items:center;justify-content:space-between;gap:.7rem;padding:.7rem;border:1px solid #e9ece6;border-radius:.65rem;color:#35473c;text-decoration:none;font-size:.78rem}.related-list>li>a:focus-visible{outline:2px solid #d77a3b;outline-offset:2px}.execution-summary{display:grid;gap:.25rem;min-width:0}.execution-summary strong{color:#45554b;font-size:.76rem}.execution-summary small{color:#8a958d;font-size:.66rem}.execution-summary p{margin:.2rem 0;color:#707c73;font-size:.72rem;line-height:1.5}.execution-summary .failure-detail{padding:.5rem;border-radius:.45rem;background:#fff2ec;color:#914a38}.failure-detail code{display:block;margin-top:.25rem;overflow-wrap:anywhere;font-size:.65rem}.identity-panel{display:flex;align-items:center;justify-content:space-between;gap:1rem;background:#f6f6ef}.identity-panel p{max-width:42rem;margin:.4rem 0 0;color:#79847c;font-size:.75rem;line-height:1.55}.identity-panel>a{flex:0 0 auto;color:#3e755f;font-size:.74rem;font-weight:700;text-decoration:none}.page-footnote{display:flex;justify-content:space-between;gap:1rem;color:#8a928c;font-size:.69rem}.page-footnote a:focus-visible,.identity-panel>a:focus-visible{outline:2px solid #d77a3b;outline-offset:3px}
@media(max-width:720px){.detail-grid{grid-template-columns:1fr}.task-hero{align-items:flex-start;flex-direction:column}.task-hero h1{font-size:1.8rem}.identity-panel{align-items:flex-start;flex-direction:column}.page-footnote{flex-direction:column}}
</style>
