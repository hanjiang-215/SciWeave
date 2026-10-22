import { fileURLToPath, URL } from 'node:url'
import { loadEnv, defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const devPort = env.VITE_DEV_PORT ? Number(env.VITE_DEV_PORT) : 0
  const previewPort = env.VITE_PREVIEW_PORT ? Number(env.VITE_PREVIEW_PORT) : 0

  return {
    plugins: [vue()],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
      },
    },
    server: {
      host: env.VITE_DEV_HOST || undefined,
      port: devPort,
      strictPort: Boolean(env.VITE_DEV_PORT),
    },
    preview: {
      host: env.VITE_PREVIEW_HOST || env.VITE_DEV_HOST || undefined,
      port: previewPort,
      strictPort: Boolean(env.VITE_PREVIEW_PORT || env.VITE_DEV_PORT),
    },
  }
})
