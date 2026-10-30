<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import StatusBadge from '@/components/StatusBadge.vue'
import { layoutTaskGraph, statusDescription, type TaskNode } from '@/domain/dashboard'

const props = defineProps<{ tasks: TaskNode[] }>()

// Fixed geometry keeps the SVG coordinate system stable so edges and cards line
// up without measuring the DOM. Units are SVG user units; the viewBox scales.
const NODE_W = 240
const NODE_H = 124
const COL_GAP = 96
const ROW_GAP = 28
const PAD_X = 28
const PAD_Y = 28

const graph = computed(() => layoutTaskGraph(props.tasks))

const positions = computed(() => {
  const map = new Map<string, { x: number; y: number }>()
  for (const node of graph.value.nodes) {
    map.set(node.task.id, {
      x: PAD_X + node.layer * (NODE_W + COL_GAP),
      y: PAD_Y + node.row * (NODE_H + ROW_GAP),
    })
  }
  return map
})

const width = computed(() => PAD_X * 2 + Math.max(graph.value.layerCount - 1, 0) * (NODE_W + COL_GAP) + NODE_W)
const height = computed(() => PAD_Y * 2 + Math.max(graph.value.maxRowsInLayer - 1, 0) * (NODE_H + ROW_GAP) + NODE_H)

function edgePath(from: string, to: string): string {
  const start = positions.value.get(from)
  const end = positions.value.get(to)
  if (!start || !end) return ''
  const x1 = start.x + NODE_W
  const y1 = start.y + NODE_H / 2
  const x2 = end.x
  const y2 = end.y + NODE_H / 2
  const midX = (x1 + x2) / 2
  // Orthogonal-ish cubic: leaves the parent horizontally and enters the child
  // horizontally, so the arrowhead always points right.
  return `M ${x1} ${y1} C ${midX} ${y1}, ${midX} ${y2}, ${x2} ${y2}`
}

function statusClass(status: TaskNode['status']): string {
  if (status === 'failed' || status === 'result_unknown') return 'danger'
  if (status === 'succeeded') return 'success'
  if (status === 'waiting' || status === 'revision_required') return 'warning'
  return 'neutral'
}
</script>

<template>
  <div class="task-map" role="group" aria-label="任务依赖思维导图">
    <svg
      class="task-map__svg"
      :viewBox="`0 0 ${width} ${height}`"
      :width="width"
      :height="height"
      role="img"
      aria-label="任务依赖关系图，节点从左向右按依赖层级发散"
    >
      <defs>
        <marker id="task-map-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M 0 0 L 10 5 L 0 10 z" fill="#9db4a6" />
        </marker>
      </defs>
      <g class="task-map__edges">
        <path
          v-for="edge in graph.edges"
          :key="`${edge.from}->${edge.to}`"
          class="task-map__edge"
          :d="edgePath(edge.from, edge.to)"
          marker-end="url(#task-map-arrow)"
        />
      </g>
      <foreignObject
        v-for="node in graph.nodes"
        :key="node.task.id"
        :x="positions.get(node.task.id)!.x"
        :y="positions.get(node.task.id)!.y"
        :width="NODE_W"
        :height="NODE_H"
        class="task-map__node-object"
      >
        <RouterLink :to="`/tasks/${node.task.id}`" class="node-card" :class="[`node-card--${statusClass(node.task.status)}`, { 'node-card--attention': node.task.attentionRank > 0 }]">
          <div class="node-card__head">
            <p class="node-card__eyebrow">TASK NODE · {{ node.task.logicalId ?? node.task.id }}</p>
            <StatusBadge :status="node.task.status" />
          </div>
          <h3 class="node-card__title">{{ node.task.name }}</h3>
          <p class="node-card__owner"><span aria-hidden="true">◔</span> 负责人：{{ node.task.owner }}</p>
          <p v-if="node.task.blockingReason" class="node-card__blocker" :title="node.task.blockingReason">↳ {{ node.task.blockingReason }}</p>
          <p v-else class="node-card__status">{{ statusDescription(node.task.status) }}</p>
        </RouterLink>
      </foreignObject>
    </svg>
  </div>
</template>

<style scoped>
.task-map {
  overflow: auto;
  border: 1px solid #e6e7e0;
  border-radius: 1rem;
  background:
    radial-gradient(circle at 1px 1px, #e3e7e1 1px, transparent 0) 0 0 / 22px 22px,
    #fffefa;
  padding: .5rem;
}
.task-map__svg { display: block; }
.task-map__edge { fill: none; stroke: #a9bcb0; stroke-width: 1.6; }
.task-map__node-object { overflow: visible; }
.node-card {
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  gap: .28rem;
  width: 100%;
  height: 100%;
  padding: .7rem .8rem;
  border: 1.5px solid #cdd8d0;
  border-radius: .8rem;
  background: #fffefa;
  color: inherit;
  text-decoration: none;
  box-shadow: 0 1px 2px rgba(27, 40, 34, .05);
  transition: border-color .16s, transform .16s, box-shadow .16s;
}
.node-card:hover { transform: translateY(-1px); border-color: #8fb09c; box-shadow: 0 6px 16px rgba(27, 40, 34, .1); }
.node-card:focus-visible { outline: 3px solid #d77a3b; outline-offset: 2px; }
.node-card--success { border-color: #b7d8c8; }
.node-card--warning { border-color: #ecd2a4; }
.node-card--danger { border-color: #eabfae; }
.node-card--attention { box-shadow: 0 0 0 3px #f7e3cd; }
.node-card__head { display: flex; align-items: center; justify-content: space-between; gap: .4rem; }
.node-card__eyebrow { margin: 0; overflow: hidden; color: #8a968e; font-size: .56rem; font-weight: 800; letter-spacing: .1em; text-overflow: ellipsis; white-space: nowrap; text-transform: uppercase; }
.node-card__head :deep(.status-badge) { flex: 0 0 auto; padding: .16rem .42rem; font-size: .6rem; }
.node-card__title { margin: 0; overflow: hidden; color: #1f2f27; font-family: Georgia, 'Noto Serif SC', serif; font-size: .92rem; font-weight: 600; line-height: 1.2; text-overflow: ellipsis; white-space: nowrap; }
.node-card__owner { display: flex; align-items: center; gap: .3rem; margin: 0; overflow: hidden; color: #5d6d63; font-size: .66rem; text-overflow: ellipsis; white-space: nowrap; }
.node-card__owner span { color: #8fae9b; }
.node-card__status { margin: 0; overflow: hidden; color: #8d978f; font-size: .62rem; text-overflow: ellipsis; white-space: nowrap; }
.node-card__blocker { display: -webkit-box; margin: 0; overflow: hidden; color: #a3611a; font-size: .62rem; line-height: 1.35; -webkit-box-orient: vertical; -webkit-line-clamp: 2; }
</style>
