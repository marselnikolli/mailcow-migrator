import React, { useEffect, useState } from 'react'
import { jobsApi, JobCreatePayload, ImportedAccount } from '../api'
import LiveLogs from '../components/LiveLogs'
import ImportModal from '../components/ImportModal'

interface Job {
  id: number
  status: string
  source_email: string
  target_email: string
  target_domain: string
  progress: number
  error_message?: string
  created_at: string
  target_type?: string
  target_host?: string
  dry_run?: boolean
}

interface AccountRow {
  key: number
  source_email: string
  source_password: string
  target_email: string
}

let nextAccountKey = 1

const Jobs: React.FC = () => {
  const [jobs, setJobs] = useState<Job[]>([])
  const [loading, setLoading] = useState(true)
  const [filterStatus, setFilterStatus] = useState<string>('all')
  const [selectedJobId, setSelectedJobId] = useState<number | null>(null)
  const [showCreateForm, setShowCreateForm] = useState(false)
  const [showImportModal, setShowImportModal] = useState(false)
  const [createError, setCreateError] = useState('')
  const [createSuccess, setCreateSuccess] = useState('')
  const [creating, setCreating] = useState(false)

  // Source server config
  const [sourceHost, setSourceHost] = useState('imap.gmail.com')
  const [sourcePort, setSourcePort] = useState(993)
  const [sourceSsl, setSourceSsl] = useState(true)

  // Accounts (source + target)
  const [accounts, setAccounts] = useState<AccountRow[]>([{ key: 0, source_email: '', source_password: '', target_email: '' }])

  // Target server config
  const [targetType, setTargetType] = useState<'imap' | 'mailcow'>('mailcow')
  const [targetHost, setTargetHost] = useState('localhost')
  const [targetPort, setTargetPort] = useState(993)
  const [targetSsl, setTargetSsl] = useState(true)
  const [mailcowUrl, setMailcowUrl] = useState('')
  const [mailcowApiKey, setMailcowApiKey] = useState('')
  const [targetDomain, setTargetDomain] = useState('')
  const [targetPassword, setTargetPassword] = useState('')
  const [dryRun, setDryRun] = useState(false)

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

  const handleAddAccount = () => {
    setAccounts((prev) => [...prev, { key: nextAccountKey++, source_email: '', source_password: '', target_email: '' }])
  }

  const handleRemoveAccount = (key: number) => {
    setAccounts((prev) => {
      const next = prev.filter((a) => a.key !== key)
      return next.length === 0 ? [{ key: nextAccountKey++, source_email: '', source_password: '', target_email: '' }] : next
    })
  }

  const handleUpdateAccount = (key: number, field: keyof AccountRow, value: string) => {
    setAccounts((prev) => prev.map((a) => (a.key === key ? { ...a, [field]: value } : a)))
  }

  const handleImport = (imported: ImportedAccount[]) => {
    const rows: AccountRow[] = imported.map((acc) => ({
      key: nextAccountKey++,
      source_email: acc.email,
      source_password: acc.password,
      target_email: targetDomain ? `${acc.email.split('@')[0]}@${targetDomain}` : '',
    }))
    setAccounts((prev) => {
      const base = prev.length === 1 && !prev[0].source_email ? [] : prev
      return [...base, ...rows]
    })
  }

  const buildJobPayload = (account: AccountRow): JobCreatePayload => {
    const targetEmail = account.target_email.trim() || (targetDomain ? `${account.source_email.split('@')[0]}@${targetDomain}` : account.source_email)
    return {
      source_email: account.source_email.trim(),
      target_email: targetEmail,
      source_password: account.source_password,
      target_password: targetPassword,
      source_server: { host: sourceHost, port: Number(sourcePort) || 993, ssl: sourceSsl },
      target_type: targetType,
      target_server: {
        host: targetType === 'mailcow' ? 'localhost' : targetHost,
        port: Number(targetPort) || 993,
        ssl: targetSsl,
      },
      mailcow_url: targetType === 'mailcow' ? mailcowUrl : undefined,
      mailcow_api_key: targetType === 'mailcow' ? mailcowApiKey : undefined,
      dry_run: dryRun,
    }
  }

  const handleCreateJob = async (e: React.FormEvent) => {
    e.preventDefault()
    setCreateError('')
    setCreateSuccess('')
    setCreating(true)

    try {
      const validAccounts = accounts.filter((a) => a.source_email.trim() && a.source_password)
      if (validAccounts.length === 0) {
        setCreateError('Please add at least one source account (email + password)')
        setCreating(false)
        return
      }

      if (targetType === 'mailcow' && (!mailcowUrl.trim() || !mailcowApiKey.trim())) {
        setCreateError('Mailcow URL and API key are required when using the Mailcow API')
        setCreating(false)
        return
      }

      if (!targetPassword) {
        setCreateError('Please set a target mailbox password')
        setCreating(false)
        return
      }

      const payloads = validAccounts.map(buildJobPayload)

      if (payloads.length === 1) {
        await jobsApi.createJob(payloads[0])
        setCreateSuccess(`Job created for ${payloads[0].source_email}${dryRun ? ' (dry run)' : ''}!`)
      } else {
        const response = await jobsApi.bulkCreateJobs(payloads)
        setCreateSuccess(`${response.data.total} jobs created${dryRun ? ' (dry run)' : ''}!`)
      }

      // Reset form
      setAccounts([{ key: nextAccountKey++, source_email: '', source_password: '', target_email: '' }])
      setTargetPassword('')
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

  const inputCls = "w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
  const labelCls = "block text-sm font-medium text-gray-700 mb-1"

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

        {showImportModal && (
          <ImportModal onClose={() => setShowImportModal(false)} onImport={handleImport} />
        )}

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
              {/* Source Server Config */}
              <div className="border-b pb-6">
                <h3 className="text-lg font-medium text-gray-900 mb-4">Source Server</h3>
                <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                  <div className="md:col-span-2">
                    <label className={labelCls}>IMAP Host</label>
                    <input
                      type="text"
                      value={sourceHost}
                      onChange={(e) => setSourceHost(e.target.value)}
                      className={inputCls}
                      placeholder="imap.gmail.com"
                      required
                    />
                  </div>
                  <div>
                    <label className={labelCls}>Port</label>
                    <input
                      type="number"
                      value={sourcePort}
                      onChange={(e) => setSourcePort(Number(e.target.value))}
                      className={inputCls}
                      placeholder="993"
                    />
                  </div>
                  <div>
                    <label className={labelCls}>SSL</label>
                    <select value={sourceSsl ? 'true' : 'false'} onChange={(e) => setSourceSsl(e.target.value === 'true')} className={inputCls}>
                      <option value="true">SSL (recommended)</option>
                      <option value="false">No SSL</option>
                    </select>
                  </div>
                </div>
              </div>

              {/* Source Accounts */}
              <div className="border-b pb-6">
                <div className="flex justify-between items-center mb-4">
                  <h3 className="text-lg font-medium text-gray-900">Source Accounts</h3>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={() => setShowImportModal(true)}
                      className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 text-sm font-medium"
                    >
                      📂 Import from File
                    </button>
                    <button
                      type="button"
                      onClick={handleAddAccount}
                      className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm font-medium"
                    >
                      + Add Account
                    </button>
                  </div>
                </div>

                {accounts.map((account, index) => (
                  <div key={account.key} className="mb-4 p-4 bg-gray-50 rounded-lg">
                    <div className="flex justify-between items-center mb-3">
                      <p className="text-sm font-medium text-gray-700">Account {index + 1}</p>
                      {accounts.length > 1 && (
                        <button
                          type="button"
                          onClick={() => handleRemoveAccount(account.key)}
                          className="text-red-500 hover:text-red-700 text-sm"
                        >
                          Remove
                        </button>
                      )}
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                      <div>
                        <label className={labelCls}>Source Email</label>
                        <input
                          type="email"
                          value={account.source_email}
                          onChange={(e) => handleUpdateAccount(account.key, 'source_email', e.target.value)}
                          className={inputCls}
                          placeholder="user@source.com"
                          required
                        />
                      </div>
                      <div>
                        <label className={labelCls}>Source Password</label>
                        <input
                          type="password"
                          value={account.source_password}
                          onChange={(e) => handleUpdateAccount(account.key, 'source_password', e.target.value)}
                          className={inputCls}
                          placeholder="••••••••"
                          required
                        />
                      </div>
                      <div>
                        <label className={labelCls}>Target Email (optional)</label>
                        <input
                          type="email"
                          value={account.target_email}
                          onChange={(e) => handleUpdateAccount(account.key, 'target_email', e.target.value)}
                          className={inputCls}
                          placeholder="auto from domain"
                        />
                      </div>
                    </div>
                  </div>
                ))}
                <p className="text-xs text-gray-500">
                  Tip: leave Target Email blank to auto-generate from the source local part and the target domain below.
                </p>
              </div>

              {/* Target Server Config */}
              <div className="border-b pb-6">
                <h3 className="text-lg font-medium text-gray-900 mb-4">Target Server</h3>

                <div className="mb-4">
                  <label className={labelCls}>Destination Type</label>
                  <div className="flex gap-3">
                    <button
                      type="button"
                      onClick={() => setTargetType('mailcow')}
                      className={`px-4 py-2 rounded-lg font-medium ${targetType === 'mailcow' ? 'bg-blue-600 text-white' : 'bg-white text-gray-700 border border-gray-300 hover:bg-gray-50'}`}
                    >
                      Mailcow (API)
                    </button>
                    <button
                      type="button"
                      onClick={() => setTargetType('imap')}
                      className={`px-4 py-2 rounded-lg font-medium ${targetType === 'imap' ? 'bg-blue-600 text-white' : 'bg-white text-gray-700 border border-gray-300 hover:bg-gray-50'}`}
                    >
                      Generic IMAP Server
                    </button>
                  </div>
                </div>

                {targetType === 'mailcow' ? (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <label className={labelCls}>Mailcow URL</label>
                      <input
                        type="text"
                        value={mailcowUrl}
                        onChange={(e) => setMailcowUrl(e.target.value)}
                        className={inputCls}
                        placeholder="https://mail.example.com"
                        required
                      />
                    </div>
                    <div>
                      <label className={labelCls}>Mailcow API Key</label>
                      <input
                        type="password"
                        value={mailcowApiKey}
                        onChange={(e) => setMailcowApiKey(e.target.value)}
                        className={inputCls}
                        placeholder="Your mailcow API key"
                        required
                      />
                      <p className="text-xs text-gray-500 mt-1">
                        Mailboxes and domains will be created automatically via the Mailcow API.
                      </p>
                    </div>
                  </div>
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div>
                      <label className={labelCls}>IMAP Host</label>
                      <input
                        type="text"
                        value={targetHost}
                        onChange={(e) => setTargetHost(e.target.value)}
                        className={inputCls}
                        placeholder="localhost"
                        required
                      />
                    </div>
                    <div>
                      <label className={labelCls}>Port</label>
                      <input
                        type="number"
                        value={targetPort}
                        onChange={(e) => setTargetPort(Number(e.target.value))}
                        className={inputCls}
                        placeholder="993"
                      />
                    </div>
                    <div>
                      <label className={labelCls}>SSL</label>
                      <select value={targetSsl ? 'true' : 'false'} onChange={(e) => setTargetSsl(e.target.value === 'true')} className={inputCls}>
                        <option value="true">SSL (recommended)</option>
                        <option value="false">No SSL</option>
                      </select>
                    </div>
                  </div>
                )}

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
                  <div>
                    <label className={labelCls}>Target Domain</label>
                    <input
                      type="text"
                      value={targetDomain}
                      onChange={(e) => setTargetDomain(e.target.value)}
                      className={inputCls}
                      placeholder="example.com"
                    />
                    <p className="text-xs text-gray-500 mt-1">
                      Used to auto-build target emails (e.g. source@old.com → source@example.com).
                    </p>
                  </div>
                  <div>
                    <label className={labelCls}>Target Mailbox Password</label>
                    <input
                      type="password"
                      value={targetPassword}
                      onChange={(e) => setTargetPassword(e.target.value)}
                      className={inputCls}
                      placeholder="New password for migrated mailboxes"
                      required
                    />
                  </div>
                </div>
              </div>

              {/* Options */}
              <div className="flex flex-wrap items-center gap-6">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={dryRun}
                    onChange={(e) => setDryRun(e.target.checked)}
                    className="rounded"
                  />
                  <span className="text-sm font-medium text-gray-700">
                    Dry run (test without transferring any data)
                  </span>
                </label>
              </div>

              <div className="flex gap-3">
                <button
                  type="submit"
                  disabled={creating}
                  className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {creating ? 'Creating...' : `Create ${accounts.filter((a) => a.source_email.trim() && a.source_password).length > 1 ? 'Jobs' : 'Job'}`}
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
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-700 uppercase">Server</th>
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
                        <td className="px-6 py-4 text-sm text-gray-600">
                          {job.target_type === 'mailcow' ? 'Mailcow API' : (job.target_host || 'IMAP')}
                          {job.dry_run && <span className="ml-2 px-2 py-0.5 rounded-full text-xs bg-purple-100 text-purple-800">DRY RUN</span>}
                        </td>
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
