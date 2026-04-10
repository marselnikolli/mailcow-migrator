import axios, { AxiosInstance } from 'axios'

const API_BASE_URL = process.env.VITE_API_URL || 'http://localhost:8000/api/v1'

const api: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
})

// Add JWT and tenant headers to all requests
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  const tenantId = localStorage.getItem('tenant_id')
  
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  
  if (tenantId) {
    config.headers['X-Tenant-ID'] = tenantId
  }
  
  return config
})

// Handle authentication errors
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token')
      localStorage.removeItem('tenant_id')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

export const authApi = {
  register: (email: string, password: string, tenantName: string) =>
    api.post('/auth/register', { email, password, tenant_name: tenantName }),
  login: (email: string, password: string, tenantId: number) =>
    api.post('/auth/login', { email, password, tenant_id: tenantId }),
  getCurrentUser: () => api.get('/auth/me'),
}

export const jobsApi = {
  createJob: (sourceEmail: string, sourcePassword: string, targetEmail: string, targetPassword: string, domain: string, sourceHost?: string) =>
    api.post('/jobs/create', { source_email: sourceEmail, source_password: sourcePassword, target_email: targetEmail, target_password: targetPassword, domain, source_host: sourceHost }),
  listJobs: (status?: string, limit = 100, offset = 0) =>
    api.get('/jobs/list', { params: { status, limit, offset } }),
  getJob: (jobId: number) =>
    api.get(`/jobs/${jobId}`),
  retryJob: (jobId: number) =>
    api.post(`/jobs/retry/${jobId}`),
}

export const domainsApi = {
  addDomain: (domain: string) =>
    api.post('/domains/add', { domain }),
  listDomains: () =>
    api.get('/domains/list'),
  validateDomain: (domain: string) =>
    api.get(`/domains/validate/${domain}`),
}

export const logsApi = {
  getLogs: (jobId: number) =>
    api.get(`/logs/${jobId}`),
  connectWebSocket: (jobId: number) => {
    const token = localStorage.getItem('token')
    const tenantId = localStorage.getItem('tenant_id')
    const wsUrl = API_BASE_URL.replace('http', 'ws').replace('/api/v1', '')
    return new WebSocket(`${wsUrl}/api/v1/logs/ws/${jobId}?token=${token}&tenant_id=${tenantId}`)
  },
}

export default api
