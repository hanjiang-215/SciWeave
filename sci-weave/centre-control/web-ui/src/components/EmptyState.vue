<script setup lang="ts">
defineProps<{ title: string; description: string }>()
</script>

<template>
  <section class="empty-state" role="status">
    <span class="empty-state__icon" aria-hidden="true">○</span>
    <h2>{{ title }}</h2>
    <p>{{ description }}</p>
  </section>
</template>

<style scoped>
.empty-state { display: grid; justify-items: center; gap: .55rem; padding: 3rem 1rem; text-align: center; color: #57615d; }
.empty-state__icon { display: grid; place-items: center; width: 2.8rem; height: 2.8rem; border: 1px solid #cbd4cf; border-radius: 50%; color: #568372; font-size: 1.6rem; }
.empty-state h2 { margin: 0; color: #1b2622; font-size: 1.1rem; }
.empty-state p { max-width: 34rem; margin: 0; font-size: .9rem; line-height: 1.6; }
</style>
