import axios, { AxiosInstance } from 'axios'

const API_BASE_URL = (import.meta.env.VITE_API_URL as string) || 'http://localhost:8000/api/v1'

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

export interface ServerConfig {
  host: string
  port: number
  ssl: boolean
}

export interface JobCreatePayload {
  source_email: string
  target_email: string
  source_password: string
  target_password: string
  source_server: ServerConfig
  target_type: 'imap' | 'mailcow'
  target_server: ServerConfig
  mailcow_url?: string
  mailcow_api_key?: string
  dry_run: boolean
  sync_calendar: boolean
  sync_contacts: boolean
}

export interface JobUpdatePayload {
  target_email?: string
  target_password?: string
  target_type?: 'imap' | 'mailcow'
  target_server?: ServerConfig
  mailcow_url?: string
  mailcow_api_key?: string
  dry_run?: boolean
  sync_calendar?: boolean
  sync_contacts?: boolean
}

export interface ImportedAccount {
  email: string
  password: string
}

export const authApi = {
  register: (email: string, password: string, tenantName: string) =>
    api.post('/auth/register', { email, password, tenant_name: tenantName }),
  login: (email: string, password: string, tenantId: number) =>
    api.post('/auth/login', { email, password, tenant_id: tenantId }),
  getCurrentUser: () => api.get('/auth/me'),
}

export const jobsApi = {
  createJob: (payload: JobCreatePayload) =>
    api.post('/jobs/create', payload),
  bulkCreateJobs: (jobs: JobCreatePayload[]) =>
    api.post('/jobs/bulk-create', { jobs }),
  importPreview: (file: File) => {
    const formData = new FormData()
    formData.append('file', file)
    return api.post('/jobs/import-preview', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  listJobs: (status?: string, limit = 100, offset = 0) =>
    api.get('/jobs/list', { params: { status, limit, offset } }),
  getJob: (jobId: number) =>
    api.get(`/jobs/${jobId}`),
  retryJob: (jobId: number) =>
    api.post(`/jobs/retry/${jobId}`),
  updateJob: (jobId: number, payload: JobUpdatePayload) =>
    api.put(`/jobs/${jobId}`, payload),
  cancelJob: (jobId: number) =>
    api.post(`/jobs/${jobId}/cancel`),
  deleteJob: (jobId: number) =>
    api.delete(`/jobs/${jobId}`),
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
    const wsUrl = API_BASE_URL.replace('http', 'ws').replace('/api/v1', '')
    const ws = new WebSocket(`${wsUrl}/api/v1/logs/ws/${jobId}`)
    // The JWT can't go in the URL (query strings end up in server/proxy logs
    // and browser history), so it's sent as the first message instead. The
    // server withholds any log data until it receives and verifies this.
    ws.addEventListener('open', () => ws.send(JSON.stringify({ token })), { once: true })
    return ws
  },
}

export default api
