<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import SourceHealth from '@/components/SourceHealth.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { attentionItems, formatInstant, statusDescription } from '@/domain/dashboard'
import { useDashboardStore } from '@/stores/dashboard'

const store = useDashboardStore()
const snapshot = computed(() => store.snapshot)
const attention = computed(() => snapshot.value ? attentionItems(snapshot.value).slice(0, 4) : [])
const completed = computed(() => snapshot.value?.tasks.filter((task) => task.status === 'succeeded').length ?? 0)
const active = computed(() => snapshot.value?.tasks.filter((task) => ['queued', 'running', 'waiting'].includes(task.status)).length ?? 0)
const failed = computed(() => snapshot.value?.tasks.filter((task) => ['failed', 'result_unknown'].includes(task.status)).length ?? 0)
const attentionCount = computed(() => snapshot.value?.tasks.filter((task) => task.attentionRank > 0).length ?? 0)

function timeLabel(value: string): string {
  return formatInstant(value, 'short')
}
</script>

<template>
  <div v-if="snapshot" class="page-stack">
    <section class="welcome-panel">
      <div class="welcome-panel__copy">
        <p class="eyebrow">RESEARCH OPERATIONS · 总览</p>
        <h1>让研究进展，一目了然。</h1>
        <p class="welcome-panel__description">跟踪路线、发现阻塞，并从准确的状态事实开始下一步协作。</p>
      </div>
      <div class="welcome-panel__project">
        <div class="project-orbit" aria-hidden="true"><span></span><span></span><span></span></div>
        <div>
          <p>当前关注项目</p>
          <strong>{{ snapshot.projects[0]?.name ?? '尚无项目' }}</strong>
          <span>{{ snapshot.projects[0]?.completed ?? 0 }} / {{ snapshot.projects[0]?.total ?? 0 }} 项任务已完成</span>
        </div>
      </div>
    </section>

    <section class="metric-grid" aria-label="研究进度摘要">
      <article class="metric-card metric-card--ink"><span>全部任务</span><strong>{{ snapshot.tasks.length.toString().padStart(2, '0') }}</strong><small>跨当前可见路线</small><i aria-hidden="true">↗</i></article>
      <article class="metric-card"><span>已完成</span><strong>{{ completed.toString().padStart(2, '0') }}</strong><small>已进入可读取状态</small><i class="metric-card__line" aria-hidden="true"></i></article>
      <article class="metric-card"><span>进行与等待</span><strong>{{ active.toString().padStart(2, '0') }}</strong><small>正在处理或等待输入</small><i class="metric-card__line metric-card__line--teal" aria-hidden="true"></i></article>
      <article class="metric-card metric-card--alert"><span>需优先核对</span><strong>{{ (attentionCount + failed).toString().padStart(2, '0') }}</strong><small>{{ failed }} 项失败或结果未知</small><i aria-hidden="true">!</i></article>
    </section>

    <div v-if="snapshot.partial" class="notice-banner" role="status"><span aria-hidden="true">◷</span><div><strong>部分来源暂不可用</strong><p>页面保留当前可读取的信息。请查看来源状态，不要把缺失数据理解为空结果。</p></div><RouterLink to="/operations">查看来源状态 <span aria-hidden="true">↗</span></RouterLink></div>

    <div class="content-grid">
      <section class="panel attention-panel">
        <header class="section-heading"><div><p class="eyebrow">需要关注</p><h2>下一步行动线索</h2></div><RouterLink to="/route" class="text-link">全部路线 <span aria-hidden="true">↗</span></RouterLink></header>
        <div v-if="attention.length" class="attention-list">
          <RouterLink v-for="(item, index) in attention" :key="item.id" class="attention-item" :to="`/tasks/${item.id}`">
            <span class="attention-item__number">0{{ index + 1 }}</span>
            <span class="attention-item__body"><strong>{{ item.title }}</strong><span>{{ item.reason }}</span></span>
            <StatusBadge :status="item.status" />
            <span class="attention-item__arrow" aria-hidden="true">↗</span>
          </RouterLink>
        </div>
        <p v-else class="quiet-empty">目前没有需要特别关注的任务。继续推进研究路线即可。</p>
      </section>

      <section class="panel source-panel">
        <header class="section-heading"><div><p class="eyebrow">系统观察</p><h2>数据来源</h2></div><RouterLink to="/operations" class="round-link" aria-label="查看全部服务状态">↗</RouterLink></header>
        <SourceHealth :sources="snapshot.sources" compact />
        <div class="service-mini-list" aria-label="消息监听服务"><article v-for="service in snapshot.services" :key="service.id"><span class="service-mini-list__mark" :class="`service-mini-list__mark--${service.status}`" aria-hidden="true"></span><div><strong>{{ service.name }}</strong><small>最近检查 {{ service.lastCheckAt ? timeLabel(service.lastCheckAt) : '未知' }}</small></div><StatusBadge :status="service.status" context="service" /></article></div>
      </section>
    </div>

    <section class="panel timeline-panel">
      <header class="section-heading"><div><p class="eyebrow">最近变化</p><h2>研究活动</h2></div><span class="panel-meta">{{ snapshot.events.length }} 条记录</span></header>
      <ol class="timeline-list">
        <li v-for="event in snapshot.events.slice(0, 5)" :key="event.id" class="timeline-entry">
          <span class="timeline-entry__marker" :class="{ 'timeline-entry__marker--alert': event.type === 'mcp_failure' }" aria-hidden="true"></span>
          <span class="timeline-entry__copy"><strong>{{ event.title }}</strong><small v-if="event.duplicate">重复投递已作幂等处理，不代表新的执行结果</small></span>
          <span class="timeline-entry__time"><time :datetime="event.occurredAt">{{ timeLabel(event.occurredAt) }}</time><small>{{ event.diagnostic ?? (event.taskId ? `关联任务 ${event.taskId}` : '平台活动') }}</small></span>
        </li>
      </ol>
    </section>

    <footer class="page-footnote"><span>看板只展示观察到的事实，不会修改任务或服务状态。</span><span>数据快照 · {{ timeLabel(snapshot.observedAt) }}</span></footer>
  </div>
</template>

<style scoped>
.page-stack { display: grid; gap: 1.25rem; }
.welcome-panel { display: grid; grid-template-columns: minmax(0,1.45fr) minmax(17rem,.8fr); gap: 2rem; min-height: 13rem; overflow: hidden; border-radius: 1.3rem; padding: 2rem 2.2rem; background: #dfe9e3; position: relative; }
.welcome-panel::after { content: ''; position: absolute; width: 24rem; height: 24rem; right: 18%; top: -17rem; border: 1px solid #c7d6cc; border-radius: 50%; box-shadow: 0 0 0 2.3rem #dfe9e3,0 0 0 2.4rem #c7d6cc,0 0 0 5.2rem #dfe9e3,0 0 0 5.3rem #c7d6cc; opacity: .7; pointer-events:none; }
.welcome-panel__copy,.welcome-panel__project { position: relative; z-index: 1; }
.eyebrow { margin: 0 0 .55rem; color: #658072; font-size: .68rem; font-weight: 800; letter-spacing: .14em; text-transform: uppercase; }
h1 { max-width: 34rem; margin: 0; color: #17251f; font-family: Georgia,'Noto Serif SC',serif; font-size: clamp(1.8rem,4vw,3rem); font-weight: 500; letter-spacing: -.055em; line-height: 1.15; }
.welcome-panel__description { max-width: 33rem; margin: .85rem 0 0; color: #56655c; font-size: .95rem; line-height: 1.65; }
.welcome-panel__project { align-self: end; display:flex; align-items:center; gap:1rem; min-height:5rem; border-left:1px solid #c1d0c5; padding-left:1.5rem; }
.welcome-panel__project div:last-child { display:grid; gap:.2rem; }
.welcome-panel__project p,.welcome-panel__project span { margin:0; color:#617267; font-size:.74rem; }
.welcome-panel__project strong { color:#1d3026; font-size:1.08rem; }
.project-orbit { position:relative; width:3.4rem;height:3.4rem;border:1px solid #91a99a;border-radius:50%;flex:0 0 auto; }
.project-orbit::before,.project-orbit::after { content:'';position:absolute;inset:.45rem;border:1px solid #a5b8aa;border-radius:50%; }
.project-orbit::after { inset:.9rem;border-color:#719482; }
.project-orbit span { position:absolute; width:.42rem;height:.42rem;border-radius:50%;background:#d97736;top:.35rem;left:1.45rem; }
.project-orbit span:nth-child(2){top:1.65rem;left:.5rem;background:#3d8373}.project-orbit span:nth-child(3){top:2.25rem;left:2.1rem;background:#b4a55d}
.metric-grid { display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.85rem; }
.metric-card { min-height:8rem;position:relative;display:flex;flex-direction:column;gap:.25rem;padding:1.1rem 1.2rem;border:1px solid #e7e6df;border-radius:1rem;background:#fffefa;overflow:hidden; }
.metric-card>span { color:#747d77;font-size:.76rem;font-weight:700; }
.metric-card strong { color:#1c2924;font-family:Georgia,serif;font-size:2.25rem;font-weight:500;letter-spacing:-.07em;line-height:1.1; }
.metric-card small { color:#89908b;font-size:.7rem; }
.metric-card i { position:absolute;right:1.1rem;top:1rem;color:#869b8e;font-size:1.2rem;font-style:normal; }
.metric-card--ink { border-color:#1a2721;background:#1a2721; }.metric-card--ink>span,.metric-card--ink small{color:#aabbb0}.metric-card--ink strong{color:#f0f5ed}.metric-card--ink i{color:#d77a3b}
.metric-card--alert{background:#fff7ef;border-color:#f0ddc5}.metric-card--alert strong,.metric-card--alert i{color:#bd6339}
.metric-card__line { position:absolute;right:1.1rem;bottom:1.2rem;width:3.4rem;height:1.1rem;border-bottom:2px solid #8eb6a3;transform:skewY(-17deg); }.metric-card__line--teal{border-color:#438b82}
.notice-banner { display:flex;align-items:center;gap:.9rem;border:1px solid #efcf99;border-radius:.9rem;padding:.85rem 1rem;background:#fff6e7;color:#885716; }.notice-banner>span{font-size:1.2rem}.notice-banner div{flex:1}.notice-banner strong{font-size:.83rem}.notice-banner p{margin:.2rem 0 0;color:#866f4d;font-size:.76rem}.notice-banner a{color:#7c4c0d;font-size:.75rem;font-weight:700;text-decoration:none;white-space:nowrap}
.content-grid { display:grid;grid-template-columns:minmax(0,1.45fr) minmax(18rem,.8fr);gap:1rem; }
.panel { min-width:0;border:1px solid #e7e6df;border-radius:1rem;background:#fffefa;padding:1.25rem; }
.section-heading { display:flex;align-items:center;justify-content:space-between;gap:1rem;margin-bottom:1rem; }.section-heading h2{margin:0;color:#1c2924;font-family:Georgia,'Noto Serif SC',serif;font-size:1.27rem;font-weight:500;letter-spacing:-.025em}.section-heading .eyebrow{margin-bottom:.25rem}.text-link,.round-link{color:#3b7160;text-decoration:none;font-size:.77rem;font-weight:700}.round-link{display:grid;place-items:center;width:2rem;height:2rem;border:1px solid #d4dfd7;border-radius:50%;font-size:1rem}.text-link:focus-visible,.round-link:focus-visible,.attention-item:focus-visible{outline:3px solid #d77a3b;outline-offset:3px}
.attention-list{display:grid}.attention-item{display:grid;grid-template-columns:2rem minmax(0,1fr) auto 1rem;align-items:center;gap:.6rem;padding:.8rem 0;border-top:1px solid #eff0ea;color:inherit;text-decoration:none}.attention-item:first-child{border-top:0}.attention-item__number{color:#99a49c;font-family:Georgia,serif;font-size:.8rem}.attention-item__body{display:grid;gap:.25rem;min-width:0}.attention-item__body strong{overflow:hidden;color:#26342e;font-size:.84rem;text-overflow:ellipsis;white-space:nowrap}.attention-item__body span{overflow:hidden;color:#78817b;font-size:.72rem;text-overflow:ellipsis;white-space:nowrap}.attention-item__arrow{color:#789185}.quiet-empty{padding:1rem 0;color:#718078;font-size:.85rem;line-height:1.6}.source-panel :deep(.sources){grid-template-columns:1fr}.service-mini-list{display:grid;gap:.45rem;margin-top:.8rem;padding-top:.8rem;border-top:1px solid #eceee8}.service-mini-list article{display:grid;grid-template-columns:.55rem minmax(0,1fr) auto;align-items:center;gap:.55rem}.service-mini-list__mark{width:.45rem;height:.45rem;border-radius:50%;background:#4b9873}.service-mini-list__mark--stale,.service-mini-list__mark--unknown{background:#d08a2e}.service-mini-list__mark--unavailable{background:#b75543}.service-mini-list article>div{display:grid;gap:.1rem;min-width:0}.service-mini-list strong{overflow:hidden;color:#48574d;font-size:.7rem;text-overflow:ellipsis;white-space:nowrap}.service-mini-list small{color:#929a93;font-size:.62rem}.service-mini-list :deep(.status-badge){font-size:.61rem;padding:.2rem .4rem}.panel-meta{color:#909891;font-size:.73rem}
.timeline-panel{padding-bottom:.7rem}.timeline-list{list-style:none;margin:0;padding:0}.timeline-entry{display:grid;grid-template-columns:1rem minmax(0,1fr) minmax(8rem,auto);align-items:start;gap:.75rem;padding:.76rem 0;border-top:1px solid #eff0ea}.timeline-entry__marker{width:.58rem;height:.58rem;margin:.3rem auto 0;border:2px solid #5c9680;border-radius:50%;background:#eff6f1;box-shadow:0 0 0 3px #e8f0ea}.timeline-entry__marker--alert{border-color:#c36346;background:#fff0eb;box-shadow:0 0 0 3px #fff1e9}.timeline-entry__copy,.timeline-entry__time{display:grid;gap:.22rem}.timeline-entry__copy strong{color:#33413a;font-size:.82rem;font-weight:650}.timeline-entry__copy small,.timeline-entry__time small{color:#929a94;font-size:.68rem}.timeline-entry__time{text-align:right}.timeline-entry__time time{color:#67736b;font-size:.72rem}.page-footnote{display:flex;justify-content:space-between;gap:1rem;padding:.1rem .2rem;color:#8a928c;font-size:.68rem}
@media(max-width:900px){.metric-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.content-grid{grid-template-columns:1fr}.welcome-panel{grid-template-columns:1fr}.welcome-panel__project{justify-self:start;align-self:auto;margin-top:.3rem}}
@media(max-width:560px){.welcome-panel{padding:1.4rem;min-height:auto}.welcome-panel__project{padding-left:0;border-left:0}.metric-card{min-height:7rem;padding:.9rem}.metric-card strong{font-size:1.9rem}.panel{padding:1rem}.attention-item{grid-template-columns:1.4rem minmax(0,1fr) auto}.attention-item__arrow{display:none}.attention-item :deep(.status-badge){font-size:.64rem;padding:.25rem .42rem}.timeline-entry{grid-template-columns:1rem minmax(0,1fr)}.timeline-entry__time{grid-column:2;text-align:left}.page-footnote{flex-direction:column}}
</style>
