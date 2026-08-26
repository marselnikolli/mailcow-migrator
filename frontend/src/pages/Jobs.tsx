import React, { useEffect, useState } from 'react'
import { jobsApi, JobCreatePayload, ImportedAccount } from '../api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Checkbox } from '@/components/ui/checkbox'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Separator } from '@/components/ui/separator'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Upload, Plus, Trash2, RefreshCw, Play, MoreHorizontal, Pencil, Ban } from 'lucide-react'
import LiveLogs from '../components/LiveLogs'
import ImportModal from '../components/ImportModal'
import EditJobDialog from '../components/EditJobDialog'
import { JobStatusBadge } from '@/lib/job-status'

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
  sync_calendar?: boolean
  sync_contacts?: boolean
}

type ConfirmKind = 'cancel' | 'delete'

interface AccountRow {
  key: number
  source_email: string
  source_password: string
  target_email: string
  target_password: string
  target_email_touched: boolean
  target_password_touched: boolean
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
  const [editingJobId, setEditingJobId] = useState<number | null>(null)
  const [confirmJob, setConfirmJob] = useState<{ job: Job; kind: ConfirmKind } | null>(null)
  const [actionError, setActionError] = useState('')
  const [actionPending, setActionPending] = useState(false)

  // Source server config
  const [sourceHost, setSourceHost] = useState('imap.gmail.com')
  const [sourcePort, setSourcePort] = useState(993)
  const [sourceSsl, setSourceSsl] = useState(true)

  // Accounts (source + target)
  const newEmptyAccount = (): AccountRow => ({
    key: nextAccountKey++,
    source_email: '',
    source_password: '',
    target_email: '',
    target_password: '',
    target_email_touched: false,
    target_password_touched: false,
  })
  const [accounts, setAccounts] = useState<AccountRow[]>([newEmptyAccount()])

  // Target server config (mailcow by default -> creates mailbox like the source)
  const [targetType, setTargetType] = useState<'imap' | 'mailcow'>('mailcow')
  const [targetHost, setTargetHost] = useState('localhost')
  const [targetPort, setTargetPort] = useState(993)
  const [targetSsl, setTargetSsl] = useState(true)
  const [mailcowUrl, setMailcowUrl] = useState('')
  const [mailcowApiKey, setMailcowApiKey] = useState('')
  const [dryRun, setDryRun] = useState(false)
  const [syncCalendar, setSyncCalendar] = useState(false)
  const [syncContacts, setSyncContacts] = useState(false)

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
    setAccounts((prev) => [...prev, newEmptyAccount()])
  }

  const handleRemoveAccount = (key: number) => {
    setAccounts((prev) => {
      const next = prev.filter((a) => a.key !== key)
      return next.length === 0 ? [newEmptyAccount()] : next
    })
  }

  // Mirror source -> target by default: same email and same password.
  const handleUpdateAccount = (key: number, field: keyof AccountRow, value: string) => {
    setAccounts((prev) =>
      prev.map((a) => {
        if (a.key !== key) return a
        const next = { ...a, [field]: value }
        if (field === 'source_email' && !a.target_email_touched) {
          next.target_email = value
        }
        if (field === 'source_password' && !a.target_password_touched) {
          next.target_password = value
        }
        return next
      })
    )
  }

  const handleMarkTargetTouched = (key: number, field: 'target_email' | 'target_password') => {
    setAccounts((prev) => prev.map((a) => (a.key === key ? { ...a, [field + '_touched']: true } : a)))
  }

  // Imported accounts mirror to the same email/password by default.
  const handleImport = (imported: ImportedAccount[]) => {
    const rows: AccountRow[] = imported.map((acc) => ({
      key: nextAccountKey++,
      source_email: acc.email,
      source_password: acc.password,
      target_email: acc.email,
      target_password: acc.password,
      target_email_touched: false,
      target_password_touched: false,
    }))
    setAccounts((prev) => {
      const base = prev.length === 1 && !prev[0].source_email ? [] : prev
      return [...base, ...rows]
    })
  }

  const buildJobPayload = (account: AccountRow): JobCreatePayload => {
    const targetEmail = account.target_email.trim() || account.source_email.trim()
    const targetPassword = account.target_password || account.source_password
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
      sync_calendar: syncCalendar,
      sync_contacts: syncContacts,
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

      const payloads = validAccounts.map(buildJobPayload)

      if (payloads.length === 1) {
        await jobsApi.createJob(payloads[0])
        setCreateSuccess(`Job created for ${payloads[0].source_email}${dryRun ? ' (dry run)' : ''}!`)
      } else {
        const response = await jobsApi.bulkCreateJobs(payloads)
        const failedAccounts: { source_email: string; error: string }[] = response.data.failed || []
        setCreateSuccess(`${response.data.total} of ${payloads.length} jobs created${dryRun ? ' (dry run)' : ''}!`)
        if (failedAccounts.length > 0) {
          setCreateError(
            `${failedAccounts.length} account${failedAccounts.length > 1 ? 's' : ''} skipped: ` +
              failedAccounts.map((f) => `${f.source_email} (${f.error})`).join('; ')
          )
        }
      }

      setAccounts([newEmptyAccount()])
      setShowCreateForm(false)

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

  const handleConfirmAction = async () => {
    if (!confirmJob) return
    setActionPending(true)
    setActionError('')
    try {
      if (confirmJob.kind === 'cancel') {
        await jobsApi.cancelJob(confirmJob.job.id)
      } else {
        await jobsApi.deleteJob(confirmJob.job.id)
      }
      setConfirmJob(null)
      fetchJobs()
    } catch (error: any) {
      setActionError(error.response?.data?.detail || `Failed to ${confirmJob.kind} job`)
    } finally {
      setActionPending(false)
    }
  }

  const inputCls = "w-full"
  const labelCls = "block text-sm font-medium text-muted-foreground mb-1"

  if (loading) {
    return <div className="flex items-center justify-center py-24 text-muted-foreground">Loading...</div>
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Migration Jobs</h1>
          <p className="text-muted-foreground">Monitor and manage mail migrations</p>
        </div>
        <Button onClick={() => setShowCreateForm(!showCreateForm)}>
          {showCreateForm ? 'Cancel' : (
            <>
              <Plus className="mr-2 h-4 w-4" />
              Create Job
            </>
          )}
        </Button>
      </div>

      {actionError && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {actionError}
        </div>
      )}

      {showImportModal && (
        <ImportModal onClose={() => setShowImportModal(false)} onImport={handleImport} />
      )}

      {showCreateForm && (
        <Card>
          <CardHeader>
            <CardTitle>Create New Migration Job</CardTitle>
            <CardDescription>
              New mailboxes are proposed with the same address and password as the source, and are
              created on the destination Mailcow server automatically.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {createError && (
              <div className="mb-4 rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
                {createError}
              </div>
            )}
            {createSuccess && (
              <div className="mb-4 rounded-lg border border-success/30 bg-success/10 px-4 py-3 text-sm text-success dark:text-success">
                {createSuccess}
              </div>
            )}

            <form onSubmit={handleCreateJob} className="space-y-6">
              {/* Source Server Config */}
              <div>
                <h3 className="text-lg font-semibold">Source Server</h3>
                <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-4">
                  <div className="md:col-span-2">
                    <label className={labelCls}>IMAP Host</label>
                    <Input
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
                    <Input
                      type="number"
                      value={sourcePort}
                      onChange={(e) => setSourcePort(Number(e.target.value))}
                      className={inputCls}
                      placeholder="993"
                    />
                  </div>
                  <div>
                    <label className={labelCls}>SSL</label>
                    <select value={sourceSsl ? 'true' : 'false'} onChange={(e) => setSourceSsl(e.target.value === 'true')} className="w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm">
                      <option value="true">SSL (recommended)</option>
                      <option value="false">No SSL</option>
                    </select>
                  </div>
                </div>
              </div>

              <Separator />

              {/* Source Accounts */}
              <div>
                <div className="flex items-center justify-between">
                  <h3 className="text-lg font-semibold">Source Accounts</h3>
                  <div className="flex gap-2">
                    <Button type="button" variant="outline" onClick={() => setShowImportModal(true)}>
                      <Upload className="mr-2 h-4 w-4" />
                      Import from File
                    </Button>
                    <Button type="button" variant="outline" onClick={handleAddAccount}>
                      <Plus className="mr-2 h-4 w-4" />
                      Add Account
                    </Button>
                  </div>
                </div>

                {accounts.map((account, index) => (
                  <div key={account.key} className="mt-4 rounded-lg border bg-muted/40 p-4">
                    <div className="mb-3 flex items-center justify-between">
                      <p className="text-sm font-medium">Account {index + 1}</p>
                      {accounts.length > 1 && (
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={() => handleRemoveAccount(account.key)}
                        >
                          <Trash2 className="h-4 w-4 text-destructive" />
                        </Button>
                      )}
                    </div>
                    <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
                      <div>
                        <label className={labelCls}>Source Email</label>
                        <Input
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
                        <Input
                          type="password"
                          value={account.source_password}
                          onChange={(e) => handleUpdateAccount(account.key, 'source_password', e.target.value)}
                          className={inputCls}
                          placeholder="••••••••"
                          required
                        />
                      </div>
                      <div>
                        <label className={labelCls}>New Mailbox Email</label>
                        <Input
                          type="email"
                          value={account.target_email}
                          onChange={(e) => handleUpdateAccount(account.key, 'target_email', e.target.value)}
                          onFocus={() => handleMarkTargetTouched(account.key, 'target_email')}
                          className={inputCls}
                          placeholder="same as source"
                        />
                      </div>
                      <div>
                        <label className={labelCls}>New Mailbox Password</label>
                        <Input
                          type="password"
                          value={account.target_password}
                          onChange={(e) => handleUpdateAccount(account.key, 'target_password', e.target.value)}
                          onFocus={() => handleMarkTargetTouched(account.key, 'target_password')}
                          className={inputCls}
                          placeholder="same as source"
                        />
                      </div>
                    </div>
                  </div>
                ))}
                <p className="mt-2 text-xs text-muted-foreground">
                  By default the new mailbox keeps the source address and password. Edit the fields
                  to override.
                </p>
              </div>

              <Separator />

              {/* Target Server Config */}
              <div>
                <h3 className="text-lg font-semibold">Destination Server</h3>

                <div className="mt-4 mb-4">
                  <label className={labelCls}>Destination Type</label>
                  <Tabs value={targetType} onValueChange={(v) => setTargetType(v as 'imap' | 'mailcow')}>
                    <TabsList>
                      <TabsTrigger value="mailcow">Mailcow (API)</TabsTrigger>
                      <TabsTrigger value="imap">Generic IMAP Server</TabsTrigger>
                    </TabsList>
                  </Tabs>
                </div>

                {targetType === 'mailcow' ? (
                  <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                    <div>
                      <label className={labelCls}>Mailcow URL</label>
                      <Input
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
                      <Input
                        type="password"
                        value={mailcowApiKey}
                        onChange={(e) => setMailcowApiKey(e.target.value)}
                        className={inputCls}
                        placeholder="Your mailcow API key"
                        required
                      />
                    </div>
                  </div>
                ) : (
                  <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
                    <div>
                      <label className={labelCls}>IMAP Host</label>
                      <Input
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
                      <Input
                        type="number"
                        value={targetPort}
                        onChange={(e) => setTargetPort(Number(e.target.value))}
                        className={inputCls}
                        placeholder="993"
                      />
                    </div>
                    <div>
                      <label className={labelCls}>SSL</label>
                      <select value={targetSsl ? 'true' : 'false'} onChange={(e) => setTargetSsl(e.target.value === 'true')} className="w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm">
                        <option value="true">SSL (recommended)</option>
                        <option value="false">No SSL</option>
                      </select>
                    </div>
                  </div>
                )}
              </div>

              <Separator />

              {/* Options */}
              <div className="flex items-center gap-2">
                <Checkbox id="dryRun" checked={dryRun} onCheckedChange={(v) => setDryRun(!!v)} />
                <Label htmlFor="dryRun" className="cursor-pointer">
                  Dry run (test without transferring any data)
                </Label>
              </div>

              <Separator />

              {/* Data to migrate */}
              <div className="space-y-3">
                <p className="text-sm font-medium text-muted-foreground">Data to migrate</p>
                <div className="flex items-center gap-2">
                  <Checkbox id="syncCalendar" checked={syncCalendar} onCheckedChange={(v) => setSyncCalendar(!!v)} />
                  <Label htmlFor="syncCalendar" className="cursor-pointer">
                    Calendar (CalDAV)
                  </Label>
                </div>
                <div className="flex items-center gap-2">
                  <Checkbox id="syncContacts" checked={syncContacts} onCheckedChange={(v) => setSyncContacts(!!v)} />
                  <Label htmlFor="syncContacts" className="cursor-pointer">
                    Address book (CardDAV)
                  </Label>
                </div>
                {targetType !== 'mailcow' && (syncCalendar || syncContacts) && (
                  <p className="text-xs text-muted-foreground">
                    Note: calendar/address book sync requires a Mailcow (API) destination.
                  </p>
                )}
              </div>

              <div className="flex gap-3">
                <Button type="submit" disabled={creating}>
                  <Play className="mr-2 h-4 w-4" />
                  {creating ? 'Creating...' : `Create ${accounts.filter((a) => a.source_email.trim() && a.source_password).length > 1 ? 'Jobs' : 'Job'}`}
                </Button>
                <Button type="button" variant="outline" onClick={() => setShowCreateForm(false)}>
                  Cancel
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      {/* Filter */}
      <Tabs value={filterStatus} onValueChange={setFilterStatus}>
        <TabsList>
          {['all', 'pending', 'running', 'completed', 'failed', 'cancelled'].map((status) => (
            <TabsTrigger key={status} value={status}>
              {status.charAt(0).toUpperCase() + status.slice(1)}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>

      {/* Jobs List */}
      <Card>
        <CardContent className="p-0">
          {jobs.length === 0 ? (
            <div className="px-6 py-12 text-center text-muted-foreground">
              <p>No jobs found.</p>
              <Button variant="link" onClick={() => setShowCreateForm(true)} className="mt-1">
                Create one now!
              </Button>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Source</TableHead>
                  <TableHead>Target</TableHead>
                  <TableHead>Server</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Created</TableHead>
                  <TableHead>Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {jobs.map((job) => (
                  <React.Fragment key={job.id}>
                    <TableRow
                      className="cursor-pointer"
                      onClick={() => setSelectedJobId(selectedJobId === job.id ? null : job.id)}
                    >
                      <TableCell className="text-sm">{job.source_email}</TableCell>
                      <TableCell className="text-sm">{job.target_email}</TableCell>
                      <TableCell className="text-sm text-muted-foreground">
                        {job.target_type === 'mailcow' ? 'Mailcow API' : (job.target_host || 'IMAP')}
                        {job.dry_run && <Badge variant="outline" className="ml-2">DRY RUN</Badge>}
                        {job.sync_calendar && <Badge variant="outline" className="ml-2">Calendar</Badge>}
                        {job.sync_contacts && <Badge variant="outline" className="ml-2">Contacts</Badge>}
                      </TableCell>
                      <TableCell><JobStatusBadge status={job.status} /></TableCell>
                      <TableCell className="text-sm text-muted-foreground">
                        {new Date(job.created_at).toLocaleString()}
                      </TableCell>
                      <TableCell onClick={(e) => e.stopPropagation()}>
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button variant="ghost" size="icon" className="h-8 w-8">
                              <MoreHorizontal className="h-4 w-4" />
                              <span className="sr-only">Job actions</span>
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            {(job.status === 'pending' || job.status === 'failed') && (
                              <DropdownMenuItem onClick={() => setEditingJobId(job.id)}>
                                <Pencil className="mr-2 h-4 w-4" />
                                Edit
                              </DropdownMenuItem>
                            )}
                            {job.status === 'failed' && (
                              <DropdownMenuItem onClick={() => handleRetryJob(job.id)}>
                                <RefreshCw className="mr-2 h-4 w-4" />
                                Retry
                              </DropdownMenuItem>
                            )}
                            {(job.status === 'pending' || job.status === 'running') && (
                              <DropdownMenuItem onClick={() => setConfirmJob({ job, kind: 'cancel' })}>
                                <Ban className="mr-2 h-4 w-4" />
                                Cancel
                              </DropdownMenuItem>
                            )}
                            {(job.status === 'pending' ||
                              job.status === 'failed' ||
                              job.status === 'completed' ||
                              job.status === 'cancelled') && (
                              <>
                                <DropdownMenuSeparator />
                                <DropdownMenuItem
                                  onClick={() => setConfirmJob({ job, kind: 'delete' })}
                                  className="text-destructive focus:text-destructive"
                                >
                                  <Trash2 className="mr-2 h-4 w-4" />
                                  Delete
                                </DropdownMenuItem>
                              </>
                            )}
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </TableCell>
                    </TableRow>
                    {selectedJobId === job.id && (
                      <TableRow>
                        <TableCell colSpan={6} className="bg-muted/40">
                          {job.error_message && (
                            <div className="mb-4 rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
                              <p className="font-semibold">Error:</p>
                              <p>{job.error_message}</p>
                            </div>
                          )}
                          <LiveLogs jobId={job.id} />
                        </TableCell>
                      </TableRow>
                    )}
                  </React.Fragment>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <EditJobDialog
        jobId={editingJobId}
        onOpenChange={(open) => !open && setEditingJobId(null)}
        onSaved={fetchJobs}
      />

      <AlertDialog open={confirmJob !== null} onOpenChange={(open) => !open && setConfirmJob(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {confirmJob?.kind === 'delete' ? 'Delete this job?' : 'Cancel this job?'}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {confirmJob?.kind === 'delete'
                ? <>This permanently removes the job for <strong>{confirmJob.job.source_email}</strong> and its logs. This can't be undone.</>
                : <>This stops the migration for <strong>{confirmJob?.job.source_email}</strong> as soon as possible. Already-transferred mail is not rolled back.</>}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={actionPending}>Back</AlertDialogCancel>
            <AlertDialogAction
              onClick={(e) => {
                e.preventDefault()
                handleConfirmAction()
              }}
              disabled={actionPending}
              className={confirmJob?.kind === 'delete' ? 'bg-destructive text-destructive-foreground hover:bg-destructive/90' : undefined}
            >
              {actionPending ? 'Working...' : confirmJob?.kind === 'delete' ? 'Delete' : 'Cancel job'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}

export default Jobs
