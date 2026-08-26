import React, { useEffect, useState } from 'react'
import { jobsApi, JobUpdatePayload } from '../api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Loader2 } from 'lucide-react'

interface EditJobDialogProps {
  jobId: number | null
  onOpenChange: (open: boolean) => void
  onSaved: () => void
}

interface JobDetail {
  target_email: string
  target_type: 'imap' | 'mailcow'
  target_host: string | null
  target_port: number | null
  target_ssl: boolean | null
  mailcow_url: string | null
  dry_run: boolean
  sync_calendar: boolean
  sync_contacts: boolean
  sync_tasks: boolean
  folders?: string | null
  maxage_days?: number | null
  since_date?: string | null
  enabled?: boolean | null
  schedule_interval_minutes?: number | null
}

const EditJobDialog: React.FC<EditJobDialogProps> = ({ jobId, onOpenChange, onSaved }) => {
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const [targetEmail, setTargetEmail] = useState('')
  const [targetPassword, setTargetPassword] = useState('')
  const [targetType, setTargetType] = useState<'imap' | 'mailcow'>('mailcow')
  const [targetHost, setTargetHost] = useState('localhost')
  const [targetPort, setTargetPort] = useState(993)
  const [targetSsl, setTargetSsl] = useState(true)
  const [mailcowUrl, setMailcowUrl] = useState('')
  const [mailcowApiKey, setMailcowApiKey] = useState('')
  const [dryRun, setDryRun] = useState(false)
  const [syncCalendar, setSyncCalendar] = useState(false)
  const [syncContacts, setSyncContacts] = useState(false)
  const [syncTasks, setSyncTasks] = useState(false)
  const [folders, setFolders] = useState('')
  const [maxageDays, setMaxageDays] = useState('')
  const [sinceDate, setSinceDate] = useState('')
  const [scheduleEnabled, setScheduleEnabled] = useState(false)
  const [scheduleInterval, setScheduleInterval] = useState('60')

  useEffect(() => {
    if (jobId === null) return
    setLoading(true)
    setError('')
    setTargetPassword('')
    setMailcowApiKey('')

    jobsApi
      .getJob(jobId)
      .then((res) => {
        const job: JobDetail = res.data
        setTargetEmail(job.target_email || '')
        setTargetType((job.target_type as 'imap' | 'mailcow') || 'mailcow')
        setTargetHost(job.target_host || 'localhost')
        setTargetPort(job.target_port || 993)
        setTargetSsl(job.target_ssl ?? true)
        setMailcowUrl(job.mailcow_url || '')
        setDryRun(!!job.dry_run)
        setSyncCalendar(!!job.sync_calendar)
        setSyncContacts(!!job.sync_contacts)
        setSyncTasks(!!job.sync_tasks)
        setFolders(job.folders || '')
        setMaxageDays(job.maxage_days != null ? String(job.maxage_days) : '')
        setSinceDate(job.since_date || '')
        setScheduleEnabled(!!job.enabled)
        setScheduleInterval(job.schedule_interval_minutes != null ? String(job.schedule_interval_minutes) : '60')
      })
      .catch(() => setError('Failed to load job details'))
      .finally(() => setLoading(false))
  }, [jobId])

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault()
    if (jobId === null) return
    setError('')
    setSaving(true)

    const payload: JobUpdatePayload = {
      target_email: targetEmail.trim(),
      target_type: targetType,
      target_server: {
        host: targetType === 'mailcow' ? 'localhost' : targetHost,
        port: Number(targetPort) || 993,
        ssl: targetSsl,
      },
      dry_run: dryRun,
      sync_calendar: syncCalendar,
      sync_contacts: syncContacts,
      sync_tasks: syncTasks,
      folders: folders.trim() || undefined,
      maxage_days: maxageDays ? Number(maxageDays) : undefined,
      since_date: sinceDate || undefined,
      enabled: scheduleEnabled,
      schedule_interval_minutes: scheduleEnabled && scheduleInterval ? Number(scheduleInterval) : undefined,
    }
    if (targetPassword) payload.target_password = targetPassword
    if (targetType === 'mailcow') {
      payload.mailcow_url = mailcowUrl.trim()
      if (mailcowApiKey) payload.mailcow_api_key = mailcowApiKey
    }

    try {
      await jobsApi.updateJob(jobId, payload)
      onSaved()
      onOpenChange(false)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to update job')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={jobId !== null} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Edit migration job</DialogTitle>
          <DialogDescription>
            Only the destination can be changed, and only while the job is pending or has failed.
            After editing a failed job, use Retry to run it again.
          </DialogDescription>
        </DialogHeader>

        {loading ? (
          <div className="flex items-center justify-center py-10 text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" />
          </div>
        ) : (
          <form onSubmit={handleSave} className="space-y-4">
            {error && (
              <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
                {error}
              </div>
            )}

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label>New mailbox email</Label>
                <Input value={targetEmail} onChange={(e) => setTargetEmail(e.target.value)} required />
              </div>
              <div className="space-y-1.5">
                <Label>New mailbox password</Label>
                <Input
                  type="password"
                  value={targetPassword}
                  onChange={(e) => setTargetPassword(e.target.value)}
                  placeholder="Leave blank to keep unchanged"
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <Label>Destination type</Label>
              <Tabs value={targetType} onValueChange={(v) => setTargetType(v as 'imap' | 'mailcow')}>
                <TabsList>
                  <TabsTrigger value="mailcow">Mailcow (API)</TabsTrigger>
                  <TabsTrigger value="imap">Generic IMAP</TabsTrigger>
                </TabsList>
              </Tabs>
            </div>

            {targetType === 'mailcow' ? (
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <Label>Mailcow URL</Label>
                  <Input
                    value={mailcowUrl}
                    onChange={(e) => setMailcowUrl(e.target.value)}
                    placeholder="https://mail.example.com"
                    required
                  />
                </div>
                <div className="space-y-1.5">
                  <Label>Mailcow API key</Label>
                  <Input
                    type="password"
                    value={mailcowApiKey}
                    onChange={(e) => setMailcowApiKey(e.target.value)}
                    placeholder="Leave blank to keep unchanged"
                  />
                </div>
              </div>
            ) : (
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                <div className="space-y-1.5 sm:col-span-2">
                  <Label>IMAP host</Label>
                  <Input value={targetHost} onChange={(e) => setTargetHost(e.target.value)} required />
                </div>
                <div className="space-y-1.5">
                  <Label>Port</Label>
                  <Input
                    type="number"
                    value={targetPort}
                    onChange={(e) => setTargetPort(Number(e.target.value))}
                  />
                </div>
              </div>
            )}

            <div className="flex items-center justify-between rounded-lg border px-4 py-3">
              <div>
                <Label htmlFor="edit-dry-run">Dry run</Label>
                <p className="text-xs text-muted-foreground">Test without transferring any data</p>
              </div>
              <Switch id="edit-dry-run" checked={dryRun} onCheckedChange={setDryRun} />
            </div>

            <div className="flex items-center justify-between rounded-lg border px-4 py-3">
              <div>
                <Label htmlFor="edit-sync-calendar">Calendar (CalDAV)</Label>
                <p className="text-xs text-muted-foreground">Migrate the mailbox's calendar</p>
              </div>
              <Switch id="edit-sync-calendar" checked={syncCalendar} onCheckedChange={setSyncCalendar} />
            </div>

            <div className="flex items-center justify-between rounded-lg border px-4 py-3">
              <div>
                <Label htmlFor="edit-sync-contacts">Address book (CardDAV)</Label>
                <p className="text-xs text-muted-foreground">Migrate the mailbox's contacts</p>
              </div>
              <Switch id="edit-sync-contacts" checked={syncContacts} onCheckedChange={setSyncContacts} />
            </div>
            <div className="flex items-center justify-between rounded-lg border px-4 py-3">
              <div>
                <Label htmlFor="edit-sync-tasks">Tasks (CalDAV VTODO)</Label>
                <p className="text-xs text-muted-foreground">Migrate the mailbox's tasks</p>
              </div>
              <Switch id="edit-sync-tasks" checked={syncTasks} onCheckedChange={setSyncTasks} />
            </div>

            <div className="space-y-1.5">
              <Label>Folders (comma-separated, empty = all)</Label>
              <Input
                value={folders}
                onChange={(e) => setFolders(e.target.value)}
                placeholder="INBOX,Sent,Archive"
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <Label>Only last N days</Label>
                <Input
                  type="number"
                  min="1"
                  value={maxageDays}
                  onChange={(e) => setMaxageDays(e.target.value)}
                  placeholder="e.g. 30"
                />
              </div>
              <div className="space-y-1.5">
                <Label>Since date</Label>
                <Input
                  type="date"
                  value={sinceDate}
                  onChange={(e) => setSinceDate(e.target.value)}
                />
              </div>
            </div>

            <div className="flex items-center justify-between rounded-lg border px-4 py-3">
              <div>
                <Label htmlFor="edit-schedule-enabled">Recurring delta sync</Label>
                <p className="text-xs text-muted-foreground">Re-run this job on a schedule</p>
              </div>
              <Switch id="edit-schedule-enabled" checked={scheduleEnabled} onCheckedChange={setScheduleEnabled} />
            </div>
            {scheduleEnabled && (
              <div className="space-y-1.5">
                <Label>Run every (minutes)</Label>
                <Input
                  type="number"
                  min="5"
                  value={scheduleInterval}
                  onChange={(e) => setScheduleInterval(e.target.value)}
                  placeholder="e.g. 60"
                />
              </div>
            )}

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={saving}>
                {saving ? 'Saving...' : 'Save changes'}
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  )
}

export default EditJobDialog
