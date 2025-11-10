import axios from 'axios'

const axiosInstance = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// 请求拦截器
axiosInstance.interceptors.request.use(
  (config) => {
    // 可以在这里添加token等
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// 响应拦截器
axiosInstance.interceptors.response.use(
  (response) => {
    return response.data
  },
  (error) => {
    if (error.response) {
      console.error('API错误:', error.response.data)
      return Promise.reject(error.response.data)
    } else if (error.request) {
      console.error('网络错误:', error.request)
      return Promise.reject({ detail: '网络错误，请检查连接' })
    } else {
      console.error('错误:', error.message)
      return Promise.reject({ detail: error.message })
    }
  }
)

export default axiosInstance

