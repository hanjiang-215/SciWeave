import { createRouter, createWebHistory, type RouterHistory } from 'vue-router'

export function createAppRouter(history: RouterHistory = createWebHistory()) {
  return createRouter({
    history,
    routes: [
      { path: '/', component: () => import('@/views/OverviewView.vue') },
      { path: '/route', component: () => import('@/views/RouteView.vue') },
      { path: '/knowledge', component: () => import('@/views/KnowledgeView.vue') },
      { path: '/operations', component: () => import('@/views/OperationsView.vue') },
      { path: '/tasks/:taskId', component: () => import('@/views/TaskDetailView.vue') },
      { path: '/:pathMatch(.*)*', redirect: '/' },
    ],
  })
}
