<script setup lang="ts">
import { computed } from 'vue'
import { statusDescription, type ExecutionStatus, type TaskStatus } from '@/domain/dashboard'

const props = withDefaults(defineProps<{ status: TaskStatus | ExecutionStatus | string; context?: 'data' | 'service'; label?: string }>(), { context: 'data', label: '' })
const label = computed(() => props.label || computedLabel(props.status, props.context))
const kind = computed(() => props.status === 'failed' || props.status === 'result_unknown' || props.status === 'unavailable' || props.status === 'rejected' || props.status === 'revoked'
  ? 'danger'
  : props.status === 'succeeded' || props.status === 'completed' || props.status === 'online' || props.status === 'formalized'
    ? 'success'
    : props.status === 'waiting' || props.status === 'stale' || props.status === 'revision_required' || props.status === 'review_pending'
      ? 'warning'
      : 'neutral')

function computedLabel(status: string, context: 'data' | 'service'): string {
  if (context === 'service') {
    return { online: '在线', stale: '检查已过期', unavailable: '服务不可用', unknown: '状态未知' }[status] ?? '状态未知'
  }
  if (status === 'online') return '在线'
  if (status === 'unknown') return '状态未知'
  if (status === 'stale') return '数据可能过期'
  if (status === 'unavailable') return '数据暂不可用'
  return statusDescription(status as TaskStatus | ExecutionStatus)
}
</script>

<template>
  <span class="status-badge" :class="`status-badge--${kind}`" :aria-label="`状态：${label}`">
    <span class="status-badge__dot" aria-hidden="true"></span>
    {{ label }}
  </span>
</template>

<style scoped>
.status-badge { display: inline-flex; align-items: center; gap: .45rem; border: 1px solid currentColor; border-radius: 999px; padding: .3rem .62rem; font-size: .72rem; font-weight: 700; letter-spacing: .01em; white-space: nowrap; }
.status-badge__dot { width: .42rem; height: .42rem; border-radius: 50%; background: currentColor; }
.status-badge--success { color: #27755f; background: #e6f5ee; }
.status-badge--warning { color: #9c5c11; background: #fff1dc; }
.status-badge--danger { color: #a43f36; background: #ffebe7; }
.status-badge--neutral { color: #53616b; background: #edf1f2; }
</style>
