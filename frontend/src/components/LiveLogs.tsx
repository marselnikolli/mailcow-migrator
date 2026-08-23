import React, { useEffect, useRef, useState } from 'react'
import { logsApi } from '../api'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'

interface LiveLogsProps {
  jobId: number
}

const LiveLogs: React.FC<LiveLogsProps> = ({ jobId }) => {
  const [logs, setLogs] = useState<string[]>([])
  const [isConnected, setIsConnected] = useState(false)
  const logsEndRef = useRef<HTMLDivElement>(null)
  const wsRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    const ws = logsApi.connectWebSocket(jobId)

    ws.onopen = () => setIsConnected(true)

    ws.onmessage = (event) => {
      const newLogs = event.data.split('\n').filter((log: string) => log.trim())
      setLogs((prevLogs) => [...prevLogs, ...newLogs])
    }

    ws.onerror = () => setIsConnected(false)
    ws.onclose = () => setIsConnected(false)

    wsRef.current = ws

    return () => {
      if (wsRef.current) wsRef.current.close()
    }
  }, [jobId])

  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs])

  return (
    <div className="rounded-lg border bg-background">
      <div className="flex items-center justify-between border-b px-4 py-3">
        <h3 className="text-sm font-semibold">Live Logs</h3>
        <Badge className={isConnected ? 'bg-green-100 text-green-800 hover:bg-green-100' : 'bg-red-100 text-red-800 hover:bg-red-100'}>
          {isConnected ? 'Connected' : 'Disconnected'}
        </Badge>
      </div>
      <ScrollArea className="h-96">
        <div className="p-4 font-mono text-xs text-muted-foreground">
          {logs.length === 0 ? (
            <p>Waiting for logs...</p>
          ) : (
            logs.map((log, index) => (
              <div key={index} className="mb-1">
                {log}
              </div>
            ))
          )}
          <div ref={logsEndRef} />
        </div>
      </ScrollArea>
    </div>
  )
}

export default LiveLogs
