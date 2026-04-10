import React, { useEffect, useState } from 'react'
import { jobsApi } from '../api'
import LiveLogs from '../components/LiveLogs'

interface Job {
  id: number
  status: string
  source_email: string
  target_email: string
  target_domain: string
  progress: number
  error_message?: string
  created_at: string
}

const Jobs: React.FC = () => {
  const [jobs, setJobs] = useState<Job[]>([])
  const [loading, setLoading] = useState(true)
  const [filterStatus, setFilterStatus] = useState<string>('all')
  const [selectedJobId, setSelectedJobId] = useState<number | null>(null)
  const [showCreateForm, setShowCreateForm] = useState(false)
  const [createError, setCreateError] = useState('')
  const [createSuccess, setCreateSuccess] = useState('')
  const [creating, setCreating] = useState(false)

  // Form state
  const [sourceEmail, setSourceEmail] = useState('')
  const [sourcePassword, setSourcePassword] = useState('')
  const [sourceHost, setSourceHost] = useState('imap.gmail.com')
  const [targetEmail, setTargetEmail] = useState('')
  const [targetPassword, setTargetPassword] = useState('')
  const [targetDomain, setTargetDomain] = useState('')

  const fetchJobs = async () => {
    try {
      const status = filterStatus === 'all' ? undefined : filterStatus
      const response = await jobsApi.listJobs(status, 50, 0)
      setJobs(response.data)
    } catch (error) {
      console.error('Failed to fetch jobs:', error)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchJobs()
    const interval = setInterval(fetchJobs, 5000)
    return () => clearInterval(interval)
  }, [filterStatus])

  const handleCreateJob = async (e: React.FormEvent) => {
    e.preventDefault()
    setCreateError('')
    setCreateSuccess('')
    setCreating(true)

    try {
      if (!sourceEmail || !sourcePassword || !targetEmail || !targetPassword || !targetDomain) {
        setCreateError('Please fill in all required fields')
        setCreating(false)
        return
      }

      await jobsApi.createJob(
        sourceEmail,
        sourcePassword,
        targetEmail,
        targetPassword,
        targetDomain,
        sourceHost || undefined
      )

      setCreateSuccess('Job created successfully! It will start processing in the background.')
      setSourceEmail('')
      setSourcePassword('')
      setSourceHost('imap.gmail.com')
      setTargetEmail('')
      setTargetPassword('')
      setTargetDomain('')
      setShowCreateForm(false)

      // Refresh jobs
      setTimeout(fetchJobs, 1000)
    } catch (error: any) {
      setCreateError(error.response?.data?.detail || 'Failed to create job')
    } finally {
      setCreating(false)
    }
  }

  const handleRetryJob = async (jobId: number) => {
    try {
      await jobsApi.retryJob(jobId)
      setCreateSuccess('Job retry requested!')
      setTimeout(fetchJobs, 1000)
    } catch (error: any) {
      setCreateError(error.response?.data?.detail || 'Failed to retry job')
    }
  }

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'running': return 'bg-blue-100 text-blue-800'
      case 'completed': return 'bg-green-100 text-green-800'
      case 'failed': return 'bg-red-100 text-red-800'
      case 'pending': return 'bg-yellow-100 text-yellow-800'
      default: return 'bg-gray-100 text-gray-800'
    }
  }

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'running': return '⏳'
      case 'completed': return '✅'
      case 'failed': return '❌'
      case 'pending': return '⏳'
      default: return '❓'
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-100 py-12 px-4 sm:px-6 lg:px-8 flex justify-center items-center">
        <div className="text-gray-600">Loading...</div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-100 py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-7xl mx-auto">
        <div className="mb-8 flex justify-between items-start">
          <div>
            <h1 className="text-3xl font-bold text-gray-900">Migration Jobs</h1>
            <p className="text-gray-600">Monitor and manage mail migrations</p>
          </div>
          <button
            onClick={() => setShowCreateForm(!showCreateForm)}
            className="px-6 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 font-medium"
          >
            {showCreateForm ? 'Cancel' : '+ Create Job'}
          </button>
        </div>

        {/* Create Job Form */}
        {showCreateForm && (
          <div className="bg-white rounded-lg shadow p-6 mb-8">
            <h2 className="text-xl font-semibold text-gray-900 mb-6">Create New Migration Job</h2>

            {createError && (
              <div className="mb-4 p-4 bg-red-100 text-red-800 rounded-lg text-sm">{createError}</div>
            )}
            {createSuccess && (
              <div className="mb-4 p-4 bg-green-100 text-green-800 rounded-lg text-sm">{createSuccess}</div>
            )}

            <form onSubmit={handleCreateJob} className="space-y-6">
              {/* Source Email Section */}
              <div className="border-b pb-6">
                <h3 className="text-lg font-medium text-gray-900 mb-4">Source Email (From)</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Email Address</label>
                    <input
                      type="email"
                      value={sourceEmail}
                      onChange={(e) => setSourceEmail(e.target.value)}
                      className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                      placeholder="source@gmail.com"
                      required
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Password</label>
                    <input
                      type="password"
                      value={sourcePassword}
                      onChange={(e) => setSourcePassword(e.target.value)}
                      className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                      placeholder="••••••••"
                      required
                    />
                  </div>
                  <div className="md:col-span-2">
                    <label className="block text-sm font-medium text-gray-700 mb-1">IMAP Server Host</label>
                    <input
                      type="text"
                      value={sourceHost}
                      onChange={(e) => setSourceHost(e.target.value)}
                      className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                      placeholder="imap.gmail.com"
                    />
                    <p className="text-xs text-gray-500 mt-1">Default: imap.gmail.com (for Gmail accounts)</p>
                  </div>
                </div>
              </div>

              {/* Target Email Section */}
              <div className="border-b pb-6">
                <h3 className="text-lg font-medium text-gray-900 mb-4">Target Email (To)</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Email Address</label>
                    <input
                      type="email"
                      value={targetEmail}
                      onChange={(e) => setTargetEmail(e.target.value)}
                      className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                      placeholder="user@example.com"
                      required
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Password</label>
                    <input
                      type="password"
                      value={targetPassword}
                      onChange={(e) => setTargetPassword(e.target.value)}
                      className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                      placeholder="••••••••"
                      required
                    />
                  </div>
                  <div className="md:col-span-2">
                    <label className="block text-sm font-medium text-gray-700 mb-1">Domain</label>
                    <input
                      type="text"
                      value={targetDomain}
                      onChange={(e) => setTargetDomain(e.target.value)}
                      className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                      placeholder="example.com"
                      required
                    />
                    <p className="text-xs text-gray-500 mt-1">Must be configured in your Mailcow instance</p>
                  </div>
                </div>
              </div>

              <div className="flex gap-3">
                <button
                  type="submit"
                  disabled={creating}
                  className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {creating ? 'Creating...' : 'Create Job'}
                </button>
                <button
                  type="button"
                  onClick={() => setShowCreateForm(false)}
                  className="px-6 py-2 bg-gray-300 text-gray-800 rounded-lg hover:bg-gray-400 font-medium"
                >
                  Cancel
                </button>
              </div>
            </form>
          </div>
        )}

        {/* Filter */}
        <div className="mb-6 flex gap-2 flex-wrap">
          {['all', 'pending', 'running', 'completed', 'failed'].map((status) => (
            <button
              key={status}
              onClick={() => setFilterStatus(status)}
              className={`px-4 py-2 rounded-lg font-medium ${
                filterStatus === status
                  ? 'bg-blue-600 text-white'
                  : 'bg-white text-gray-700 border border-gray-300 hover:bg-gray-50'
              }`}
            >
              {status.charAt(0).toUpperCase() + status.slice(1)}
            </button>
          ))}
        </div>

        {/* Jobs List */}
        <div className="bg-white rounded-lg shadow overflow-hidden">
          {jobs.length === 0 ? (
            <div className="px-6 py-12 text-center text-gray-500">
              <p>No jobs found. <button onClick={() => setShowCreateForm(true)} className="text-blue-600 hover:text-blue-700">Create one now!</button></p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-gray-200 bg-gray-50">
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-700 uppercase">Source</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-700 uppercase">Target</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-700 uppercase">Domain</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-700 uppercase">Status</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-700 uppercase">Created</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-700 uppercase">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {jobs.map((job) => (
                    <React.Fragment key={job.id}>
                      <tr className="border-b border-gray-200 hover:bg-gray-50 cursor-pointer" onClick={() => setSelectedJobId(selectedJobId === job.id ? null : job.id)}>
                        <td className="px-6 py-4 text-sm text-gray-900">{job.source_email}</td>
                        <td className="px-6 py-4 text-sm text-gray-900">{job.target_email}</td>
                        <td className="px-6 py-4 text-sm text-gray-900">{job.target_domain}</td>
                        <td className="px-6 py-4 text-sm">
                          <span className={`px-3 py-1 rounded-full text-xs font-medium ${getStatusColor(job.status)}`}>
                            {getStatusIcon(job.status)} {job.status}
                          </span>
                        </td>
                        <td className="px-6 py-4 text-sm text-gray-600">
                          {new Date(job.created_at).toLocaleString()}
                        </td>
                        <td className="px-6 py-4 text-sm">
                          {job.status === 'failed' && (
                            <button
                              onClick={(e) => {
                                e.stopPropagation()
                                handleRetryJob(job.id)
                              }}
                              className="text-blue-600 hover:text-blue-700 font-medium"
                            >
                              Retry
                            </button>
                          )}
                        </td>
                      </tr>
                      {selectedJobId === job.id && (
                        <tr className="bg-gray-50">
                          <td colSpan={6} className="px-6 py-4">
                            {job.error_message && (
                              <div className="mb-4 p-4 bg-red-100 text-red-800 rounded-lg">
                                <p className="font-semibold">Error:</p>
                                <p>{job.error_message}</p>
                              </div>
                            )}
                            <LiveLogs jobId={job.id} />
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default Jobs
