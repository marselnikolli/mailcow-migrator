import React, { useEffect, useState } from 'react'
import { jobsApi } from '../api'
import LiveLogs from '../components/LiveLogs'

interface Job {
  id: number
  status: string
  source_email: string
  target_email: string
  progress: number
  error_message?: string
  created_at: string
}

const Jobs: React.FC = () => {
  const [jobs, setJobs] = useState<Job[]>([])
  const [loading, setLoading] = useState(true)
  const [filterStatus, setFilterStatus] = useState<string>('all')
  const [selectedJobId, setSelectedJobId] = useState<number | null>(null)

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

  const handleRetryJob = async (jobId: number) => {
    try {
      await jobsApi.retryJob(jobId)
      fetchJobs()
    } catch (error) {
      console.error('Failed to retry job:', error)
    }
  }

  if (loading) {
    return <div className="flex justify-center items-center h-screen">Loading...</div>
  }

  return (
    <div className="min-h-screen bg-gray-100 py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-7xl mx-auto">
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900">Migration Jobs</h1>
          <p className="text-gray-600">Monitor and manage mail migrations</p>
        </div>

        {/* Filter */}
        <div className="mb-6 flex gap-2">
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
              <p>No jobs found</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-gray-200 bg-gray-50">
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-700 uppercase tracking-wider">
                      Source
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-700 uppercase tracking-wider">
                      Target
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-700 uppercase tracking-wider">
                      Status
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-700 uppercase tracking-wider">
                      Progress
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-700 uppercase tracking-wider">
                      Created
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-700 uppercase tracking-wider">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {jobs.map((job) => (
                    <React.Fragment key={job.id}>
                      <tr className="border-b border-gray-200 hover:bg-gray-50 cursor-pointer"
                          onClick={() => setSelectedJobId(selectedJobId === job.id ? null : job.id)}>
                        <td className="px-6 py-4 text-sm text-gray-900">{job.source_email}</td>
                        <td className="px-6 py-4 text-sm text-gray-900">{job.target_email}</td>
                        <td className="px-6 py-4 text-sm">
                          <span
                            className={`px-3 py-1 rounded-full text-xs font-semibold ${
                              job.status === 'completed'
                                ? 'bg-green-100 text-green-800'
                                : job.status === 'failed'
                                ? 'bg-red-100 text-red-800'
                                : job.status === 'running'
                                ? 'bg-blue-100 text-blue-800'
                                : 'bg-gray-100 text-gray-800'
                            }`}
                          >
                            {job.status}
                          </span>
                        </td>
                        <td className="px-6 py-4 text-sm">
                          <div className="w-24 bg-gray-200 rounded-full h-2">
                            <div
                              className="bg-blue-600 h-2 rounded-full"
                              style={{ width: `${job.progress}%` }}
                            ></div>
                          </div>
                        </td>
                        <td className="px-6 py-4 text-sm text-gray-500">
                          {new Date(job.created_at).toLocaleDateString()}
                        </td>
                        <td className="px-6 py-4 text-sm">
                          {job.status === 'failed' && (
                            <button
                              onClick={(e) => {
                                e.stopPropagation()
                                handleRetryJob(job.id)
                              }}
                              className="px-3 py-1 bg-blue-600 text-white rounded hover:bg-blue-700 text-xs font-medium"
                            >
                              Retry
                            </button>
                          )}
                        </td>
                      </tr>
                      {selectedJobId === job.id && (
                        <tr className="bg-gray-50 border-b border-gray-200">
                          <td colSpan={6} className="px-6 py-4">
                            <div className="mb-4">
                              {job.error_message && (
                                <div className="mb-4 p-4 bg-red-100 text-red-800 rounded-lg">
                                  <p className="font-semibold">Error:</p>
                                  <p>{job.error_message}</p>
                                </div>
                              )}
                            </div>
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
