import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  // 加载环境变量
  const env = loadEnv(mode, process.cwd(), '')
  
  return {
    plugins: [react()],
    server: {
      host: '0.0.0.0', // 允许外部访问（Docker需要）
      port: 5173,
      proxy: {
        '/api': {
          // 在Docker容器中，使用服务名访问后端；本地开发时使用localhost
          // Vite代理在开发服务器端执行，所以使用容器内部的服务名
          target: env.VITE_API_BASE_URL || 'http://localhost:8000',
          changeOrigin: true
        }
      }
    }
  }
})

