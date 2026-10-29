<script setup lang="ts">
import type { DataSource } from '@/domain/dashboard'
import { formatInstant, sourceLabel } from '@/domain/dashboard'

withDefaults(defineProps<{ sources: DataSource[]; compact?: boolean }>(), { compact: false })

function displayTime(value?: string): string {
  if (!value) return '更新时间未知'
  return formatInstant(value, 'time')
}
</script>

<template>
  <section class="sources" aria-label="数据来源状态">
    <article v-for="source in sources" :key="source.id" class="source" :class="`source--${source.status}`">
      <span class="source__indicator" aria-hidden="true"></span>
      <span class="source__body">
        <strong>{{ source.label }}</strong>
        <span>{{ sourceLabel(source) }} · {{ displayTime(source.observedAt) }}</span>
        <small v-if="source.error && !compact">{{ source.error }}</small>
      </span>
      <span v-if="source.status !== 'fresh'" class="source__status">{{ sourceLabel(source) }}</span>
    </article>
  </section>
</template>

<style scoped>
.sources { display: grid; gap: .65rem; }
.source { display: flex; align-items: flex-start; gap: .7rem; min-width: 0; padding: .75rem .8rem; border: 1px solid #e5e7e3; border-radius: .8rem; background: #fffefa; }
.source__indicator { width: .55rem; height: .55rem; margin-top: .3rem; border-radius: 50%; background: #38856e; flex: 0 0 auto; }
.source--stale .source__indicator, .source--partial .source__indicator { background: #d88b27; }
.source--unavailable .source__indicator { background: #b34e40; }
.source__body { display: grid; gap: .18rem; min-width: 0; }
.source__body strong { font-size: .83rem; }
.source__body span, .source__body small { color: #68716e; font-size: .72rem; overflow-wrap: anywhere; }
.source__status { margin-left: auto; color: #85550f; font-size: .68rem; text-align: right; }
</style>
