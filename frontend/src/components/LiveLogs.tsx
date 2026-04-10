import React, { useEffect, useRef, useState } from 'react'
import { logsApi } from '../api'

interface LiveLogsProps {
  jobId: number
}

const LiveLogs: React.FC<LiveLogsProps> = ({ jobId }) => {
  const [logs, setLogs] = useState<string[]>([])
  const [isConnected, setIsConnected] = useState(false)
  const logsEndRef = useRef<HTMLDivElement>(null)
  const wsRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    // Connect to WebSocket for real-time logs
    const ws = logsApi.connectWebSocket(jobId)

    ws.onopen = () => {
      setIsConnected(true)
    }

    ws.onmessage = (event) => {
      const newLogs = event.data.split('\n').filter((log: string) => log.trim())
      setLogs((prevLogs) => [...prevLogs, ...newLogs])
    }

    ws.onerror = () => {
      setIsConnected(false)
    }

    ws.onclose = () => {
      setIsConnected(false)
    }

    wsRef.current = ws

    return () => {
      if (wsRef.current) {
        wsRef.current.close()
      }
    }
  }, [jobId])

  // Auto-scroll to bottom when new logs arrive
  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs])

  return (
    <div className="bg-gray-900 text-gray-100 p-4 rounded-lg font-mono text-sm max-h-96 overflow-y-auto">
      <div className="flex justify-between items-center mb-4">
        <h3 className="font-bold">Live Logs</h3>
        <span className={`px-2 py-1 rounded text-xs ${isConnected ? 'bg-green-600' : 'bg-red-600'}`}>
          {isConnected ? 'Connected' : 'Disconnected'}
        </span>
      </div>
      <div>
        {logs.length === 0 ? (
          <p className="text-gray-500">Waiting for logs...</p>
        ) : (
          logs.map((log, index) => (
            <div key={index} className="mb-1">
              {log}
            </div>
          ))
        )}
        <div ref={logsEndRef} />
      </div>
    </div>
  )
}

export default LiveLogs
