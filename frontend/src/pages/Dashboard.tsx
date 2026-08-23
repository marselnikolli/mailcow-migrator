import React, { useEffect, useState } from 'react'
import { jobsApi } from '../api'
import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Play, Mail, FolderOpen, Activity, AlertCircle, CheckCircle2 } from 'lucide-react'
import { JobStatusBadge } from '@/lib/job-status'

interface Job {
  id: number
  status: string
  source_email: string
  target_email: string
  progress: number
  created_at: string
  dry_run?: boolean
}

const Dashboard: React.FC = () => {
  const [stats, setStats] = useState({ active: 0, failed: 0, completed: 0 })
  const [recentJobs, setRecentJobs] = useState<Job[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchData = async () => {
      try {
        const response = await jobsApi.listJobs(undefined, 10, 0)
        const jobs = response.data

        const stats = {
          active: jobs.filter((j: Job) => j.status === 'running' || j.status === 'pending').length,
          failed: jobs.filter((j: Job) => j.status === 'failed').length,
          completed: jobs.filter((j: Job) => j.status === 'completed').length,
        }

        setStats(stats)
        setRecentJobs(jobs.slice(0, 10))
      } catch (error) {
        console.error('Failed to fetch jobs:', error)
      } finally {
        setLoading(false)
      }
    }

    fetchData()
    const interval = setInterval(fetchData, 5000)
    return () => clearInterval(interval)
  }, [])

  if (loading) {
    return <div className="flex items-center justify-center py-24 text-muted-foreground">Loading...</div>
  }

  const statCards = [
    { label: 'Active Migrations', value: stats.active, icon: Activity, color: 'text-blue-600' },
    { label: 'Failed Jobs', value: stats.failed, icon: AlertCircle, color: 'text-red-600' },
    { label: 'Completed', value: stats.completed, icon: CheckCircle2, color: 'text-green-600' },
  ]

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-muted-foreground">Mail migration analytics and overview</p>
      </div>

      <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
        {statCards.map((card) => {
          const Icon = card.icon
          return (
            <Card key={card.label}>
              <CardContent className="flex items-center justify-between p-6">
                <div>
                  <p className="text-sm font-medium text-muted-foreground">{card.label}</p>
                  <p className={`text-3xl font-bold ${card.color}`}>{card.value}</p>
                </div>
                <Icon className={`h-8 w-8 ${card.color}`} />
              </CardContent>
            </Card>
          )
        })}
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Quick Actions</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-3">
          <Link to="/jobs">
            <Button>
              <Play className="mr-2 h-4 w-4" />
              Create New Migration Job
            </Button>
          </Link>
          <Link to="/domains">
            <Button variant="outline">
              <FolderOpen className="mr-2 h-4 w-4" />
              Manage Domains
            </Button>
          </Link>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Recent Migrations</CardTitle>
        </CardHeader>
        <CardContent>
          {recentJobs.length === 0 ? (
            <div className="py-8 text-center text-muted-foreground">
              <Mail className="mx-auto mb-2 h-8 w-8 text-muted-foreground/50" />
              <p>No jobs yet. <Link to="/jobs" className="text-primary hover:underline">Create one now!</Link></p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Source</TableHead>
                  <TableHead>Target</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Created</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {recentJobs.map((job) => (
                  <TableRow key={job.id}>
                    <TableCell className="text-sm">{job.source_email}</TableCell>
                    <TableCell className="text-sm">{job.target_email}</TableCell>
                    <TableCell>
                      <JobStatusBadge status={job.status} />
                      {job.dry_run && <Badge variant="outline" className="ml-1">dry run</Badge>}
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {new Date(job.created_at).toLocaleString()}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

export default Dashboard
