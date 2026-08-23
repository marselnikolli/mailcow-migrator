import React, { useEffect, useState } from 'react'
import { domainsApi } from '../api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { CheckCircle2, CircleDashed } from 'lucide-react'

interface Domain {
  id: number
  domain: string
  created_in_mailcow: boolean
  created_at: string
}

const Domains: React.FC = () => {
  const [domains, setDomains] = useState<Domain[]>([])
  const [newDomain, setNewDomain] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [adding, setAdding] = useState(false)

  const fetchDomains = async () => {
    try {
      const response = await domainsApi.listDomains()
      setDomains(response.data)
    } catch (err) {
      setError('Failed to fetch domains')
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchDomains()
  }, [])

  const handleAddDomain = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setSuccess('')
    setAdding(true)

    if (!newDomain) {
      setError('Please enter a domain name')
      setAdding(false)
      return
    }

    try {
      await domainsApi.addDomain(newDomain)
      setSuccess(`Domain ${newDomain} added successfully`)
      setNewDomain('')
      fetchDomains()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to add domain')
    } finally {
      setAdding(false)
    }
  }

  if (loading) {
    return <div className="flex items-center justify-center py-24 text-muted-foreground">Loading...</div>
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Domain Management</h1>
        <p className="text-muted-foreground">Manage and monitor email domains</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Add New Domain</CardTitle>
          <CardDescription>
            Domain must exist in your Mailcow instance before it can be used for migrations
          </CardDescription>
        </CardHeader>
        <CardContent>
          {error && (
            <div className="mb-4 rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
              {error}
            </div>
          )}
          {success && (
            <div className="mb-4 rounded-lg border border-success/30 bg-success/10 px-4 py-3 text-sm text-success dark:text-success">
              {success}
            </div>
          )}

          <form onSubmit={handleAddDomain} className="flex gap-2">
            <Input
              type="text"
              placeholder="example.com"
              value={newDomain}
              onChange={(e) => setNewDomain(e.target.value)}
              className="flex-1"
              required
            />
            <Button type="submit" disabled={adding}>
              {adding ? 'Adding...' : 'Add Domain'}
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Configured Domains</CardTitle>
        </CardHeader>
        <CardContent>
          {domains.length === 0 ? (
            <div className="py-8 text-center text-muted-foreground">
              <p>No domains added yet. Add your first domain above.</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Domain</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Added</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {domains.map((domain) => (
                  <TableRow key={domain.id}>
                    <TableCell className="font-medium">{domain.domain}</TableCell>
                    <TableCell>
                      {domain.created_in_mailcow ? (
                        <Badge className="border-transparent bg-success/15 text-success dark:text-success">
                          <CheckCircle2 className="mr-1 h-3 w-3" />
                          Active
                        </Badge>
                      ) : (
                        <Badge className="border-transparent bg-amber-500/15 text-amber-700 dark:text-amber-400">
                          <CircleDashed className="mr-1 h-3 w-3" />
                          Pending
                        </Badge>
                      )}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {new Date(domain.created_at).toLocaleString()}
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

export default Domains
