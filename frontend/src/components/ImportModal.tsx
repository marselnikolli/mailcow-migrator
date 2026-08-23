import React, { useRef, useState } from 'react'
import { jobsApi, ImportedAccount } from '../api'

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
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-lg shadow-xl max-w-3xl w-full max-h-[80vh] flex flex-col">
        <div className="px-6 py-4 border-b border-gray-200 flex justify-between items-center">
          <h2 className="text-xl font-semibold text-gray-900">Import Accounts from File</h2>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-700 text-xl">&times;</button>
        </div>

        <div className="px-6 py-4 overflow-y-auto flex-1">
          {error && (
            <div className="mb-4 p-4 bg-red-100 text-red-800 rounded-lg text-sm">{error}</div>
          )}

          <div className="mb-4">
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Upload CSV, XLSX, or JSON file
            </label>
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv,.xlsx,.xlsm,.json,.txt"
              onChange={handleFileChange}
              className="w-full px-4 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <p className="text-xs text-gray-500 mt-1">
              Expected columns: <span className="font-mono">email</span> and{' '}
              <span className="font-mono">password</span>. JSON may be a list of{' '}
              <span className="font-mono">{'{email, password}'}</span> objects or a dict of{' '}
              <span className="font-mono">{'{email: password}'}</span>.
            </p>
          </div>

          {loading && <div className="text-gray-600 text-sm py-4">Parsing file...</div>}

          {!loading && accounts.length > 0 && (
            <div>
              <div className="flex justify-between items-center mb-3">
                <p className="text-sm text-gray-700">
                  Found <span className="font-semibold">{accounts.length}</span> accounts in{' '}
                  <span className="font-mono">{fileName}</span>
                </p>
                <button
                  onClick={toggleAll}
                  className="text-sm text-blue-600 hover:text-blue-700 font-medium"
                >
                  {selected.size === accounts.length ? 'Deselect all' : 'Select all'}
                </button>
              </div>

              <div className="border border-gray-200 rounded-lg overflow-hidden max-h-64 overflow-y-auto">
                <table className="w-full text-sm">
                  <thead className="bg-gray-50">
                    <tr className="border-b border-gray-200">
                      <th className="px-3 py-2 text-left font-medium text-gray-700 w-8">
                        <input
                          type="checkbox"
                          checked={accounts.length > 0 && selected.size === accounts.length}
                          onChange={toggleAll}
                          className="rounded"
                        />
                      </th>
                      <th className="px-3 py-2 text-left font-medium text-gray-700">Email</th>
                      <th className="px-3 py-2 text-left font-medium text-gray-700">Password</th>
                    </tr>
                  </thead>
                  <tbody>
                    {accounts.map((account, index) => (
                      <tr
                        key={index}
                        className={`border-b border-gray-100 ${selected.has(index) ? 'bg-blue-50' : ''}`}
                        onClick={() => toggleOne(index)}
                        style={{ cursor: 'pointer' }}
                      >
                        <td className="px-3 py-2">
                          <input
                            type="checkbox"
                            checked={selected.has(index)}
                            onChange={() => toggleOne(index)}
                            onClick={(e) => e.stopPropagation()}
                            className="rounded"
                          />
                        </td>
                        <td className="px-3 py-2 text-gray-900">{account.email}</td>
                        <td className="px-3 py-2 text-gray-600 font-mono">
                          {account.password ? '••••••' : ''}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {!loading && accounts.length === 0 && fileName && (
            <div className="text-gray-500 text-sm py-4">No accounts found in this file.</div>
          )}
        </div>

        <div className="px-6 py-4 border-t border-gray-200 flex justify-end gap-3">
          <button
            onClick={onClose}
            className="px-6 py-2 bg-gray-300 text-gray-800 rounded-lg hover:bg-gray-400 font-medium"
          >
            Cancel
          </button>
          <button
            onClick={handleImport}
            disabled={selected.size === 0}
            className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Import Selected ({selected.size})
          </button>
        </div>
      </div>
    </div>
  )
}

export default ImportModal
