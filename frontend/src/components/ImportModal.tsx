import React, { useRef, useState } from 'react'
import { jobsApi, ImportedAccount } from '../api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Upload } from 'lucide-react'

interface ImportModalProps {
  onClose: () => void
  onImport: (accounts: ImportedAccount[]) => void
}

const ImportModal: React.FC<ImportModalProps> = ({ onClose, onImport }) => {
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [accounts, setAccounts] = useState<ImportedAccount[]>([])
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [fileName, setFileName] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    setLoading(true)
    setError('')
    setFileName(file.name)
    setAccounts([])
    setSelected(new Set())

    try {
      const response = await jobsApi.importPreview(file)
      const data = response.data
      setAccounts(data.accounts || [])
      setSelected(new Set(data.accounts.map((_: ImportedAccount, i: number) => i)))
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to parse file')
    } finally {
      setLoading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  const toggleAll = () => {
    if (selected.size === accounts.length) {
      setSelected(new Set())
    } else {
      setSelected(new Set(accounts.map((_, i) => i)))
    }
  }

  const toggleOne = (index: number) => {
    const next = new Set(selected)
    if (next.has(index)) {
      next.delete(index)
    } else {
      next.add(index)
    }
    setSelected(next)
  }

  const handleImport = () => {
    const chosen = accounts.filter((_, i) => selected.has(i))
    onImport(chosen)
    onClose()
  }

  return (
    <Dialog open onOpenChange={(open) => { if (!open) onClose() }}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>Import Accounts from File</DialogTitle>
          <DialogDescription>
            Upload a CSV, XLSX, or JSON file and select the accounts you want to import. The new
            mailboxes will keep the same address and password by default.
          </DialogDescription>
        </DialogHeader>

        {error && (
          <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            {error}
          </div>
        )}

        <div>
          <label className="mb-2 block text-sm font-medium text-muted-foreground">
            Upload CSV, XLSX, or JSON file
          </label>
          <Input
            ref={fileInputRef}
            type="file"
            accept=".csv,.xlsx,.xlsm,.json,.txt"
            onChange={handleFileChange}
            className="cursor-pointer"
          />
          <p className="mt-1 text-xs text-muted-foreground">
            Expected columns: <span className="font-mono">email</span> and{' '}
            <span className="font-mono">password</span>. JSON may be a list of{' '}
            <span className="font-mono">{'{email, password}'}</span> objects or a dict of{' '}
            <span className="font-mono">{'{email: password}'}</span>.
          </p>
        </div>

        {loading && <div className="py-4 text-sm text-muted-foreground">Parsing file...</div>}

        {!loading && accounts.length > 0 && (
          <div>
            <div className="mb-3 flex items-center justify-between">
              <p className="text-sm text-muted-foreground">
                Found <span className="font-semibold text-foreground">{accounts.length}</span> accounts in{' '}
                <span className="font-mono">{fileName}</span>
              </p>
              <Button variant="link" size="sm" onClick={toggleAll} className="h-auto px-0">
                {selected.size === accounts.length ? 'Deselect all' : 'Select all'}
              </Button>
            </div>

            <div className="max-h-64 overflow-y-auto rounded-lg border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-10">
                      <Checkbox
                        checked={accounts.length > 0 && selected.size === accounts.length}
                        onCheckedChange={toggleAll}
                      />
                    </TableHead>
                    <TableHead>Email</TableHead>
                    <TableHead>Password</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {accounts.map((account, index) => (
                    <TableRow
                      key={index}
                      className="cursor-pointer"
                      data-state={selected.has(index) ? 'selected' : undefined}
                      onClick={() => toggleOne(index)}
                    >
                      <TableCell>
                        <Checkbox
                          checked={selected.has(index)}
                          onCheckedChange={() => toggleOne(index)}
                        />
                      </TableCell>
                      <TableCell className="text-sm">{account.email}</TableCell>
                      <TableCell className="font-mono text-sm text-muted-foreground">
                        {account.password ? '••••••' : ''}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </div>
        )}

        {!loading && accounts.length === 0 && fileName && (
          <div className="py-4 text-sm text-muted-foreground">No accounts found in this file.</div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={handleImport} disabled={selected.size === 0}>
            <Upload className="mr-2 h-4 w-4" />
            Import Selected ({selected.size})
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default ImportModal
