<script setup lang="ts">
withDefaults(defineProps<{ title?: string; message: string; busy?: boolean }>(), { title: '暂时无法更新', busy: false })
defineEmits<{ retry: [] }>()
</script>

<template>
  <section class="error-state" role="alert">
    <div>
      <strong>{{ title }}</strong>
      <p>{{ message }}</p>
    </div>
    <button type="button" :disabled="busy" @click="$emit('retry')">{{ busy ? '正在刷新…' : '重新加载' }}</button>
  </section>
</template>

<style scoped>
.error-state { display: flex; align-items: center; justify-content: space-between; gap: 1.2rem; padding: 1rem 1.1rem; border: 1px solid #e5b3a7; border-radius: .85rem; background: #fff0eb; color: #723b32; }
.error-state p { margin: .35rem 0 0; font-size: .84rem; line-height: 1.5; }
.error-state button { border: 1px solid #9b4f43; border-radius: .6rem; padding: .6rem .85rem; background: #fffaf7; color: #783d33; font: inherit; font-weight: 700; cursor: pointer; }
.error-state button:disabled { opacity: .6; cursor: wait; }
@media (max-width: 36rem) { .error-state { align-items: flex-start; flex-direction: column; } }
</style>
