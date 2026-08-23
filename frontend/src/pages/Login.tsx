import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { authApi } from '../api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Mail } from 'lucide-react'

const Login: React.FC = () => {
  const navigate = useNavigate()
  const [isRegister, setIsRegister] = useState(false)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [tenantName, setTenantName] = useState('')
  const [tenantId, setTenantId] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)

    try {
      if (!tenantId) {
        setError('Please enter tenant ID')
        return
      }

      const response = await authApi.login(email, password, parseInt(tenantId))
      const data = response.data

      localStorage.setItem('token', data.access_token)
      localStorage.setItem('tenant_id', data.tenant_id)
      localStorage.setItem('user_id', data.user_id)
      localStorage.setItem('role', data.role)

      navigate('/')
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Login failed')
    } finally {
      setLoading(false)
    }
  }

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)

    try {
      if (!tenantName) {
        setError('Please enter tenant name')
        return
      }

      const response = await authApi.register(email, password, tenantName)
      const data = response.data

      localStorage.setItem('token', data.access_token)
      localStorage.setItem('tenant_id', data.tenant_id)
      localStorage.setItem('user_id', data.user_id)
      localStorage.setItem('role', data.role)

      navigate('/')
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Registration failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-muted/40 px-4">
      <Card className="w-full max-w-md">
        <CardHeader className="text-center">
          <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-lg bg-primary text-primary-foreground">
            <Mail className="h-6 w-6" />
          </div>
          <CardTitle className="text-2xl">mailcow-migrator</CardTitle>
          <CardDescription>Mail Migration as a Service</CardDescription>
        </CardHeader>

        <CardContent>
          {error && (
            <div className="mb-4 rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
              {error}
            </div>
          )}

          <form onSubmit={isRegister ? handleRegister : handleLogin} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                required
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                required
              />
            </div>

            {isRegister ? (
              <div className="space-y-2">
                <Label htmlFor="tenantName">Tenant Name</Label>
                <Input
                  id="tenantName"
                  type="text"
                  value={tenantName}
                  onChange={(e) => setTenantName(e.target.value)}
                  placeholder="My Company"
                  required
                />
              </div>
            ) : (
              <div className="space-y-2">
                <Label htmlFor="tenantId">Tenant ID</Label>
                <Input
                  id="tenantId"
                  type="number"
                  value={tenantId}
                  onChange={(e) => setTenantId(e.target.value)}
                  placeholder="1"
                  required
                />
              </div>
            )}

            <Button type="submit" className="w-full" disabled={loading}>
              {loading ? 'Loading...' : isRegister ? 'Create Account' : 'Login'}
            </Button>
          </form>

          <div className="mt-4 text-center text-sm text-muted-foreground">
            {isRegister ? 'Already have an account?' : "Don't have an account?"}
            <Button
              variant="link"
              className="px-1"
              onClick={() => setIsRegister(!isRegister)}
            >
              {isRegister ? 'Login' : 'Register'}
            </Button>
          </div>

          {isRegister && (
            <div className="mt-4 rounded-lg border bg-muted px-4 py-3 text-xs text-muted-foreground">
              <p className="mb-1 font-medium">✓ Creating a new account:</p>
              <ul className="list-inside list-disc space-y-1">
                <li>Creates a new tenant (organization)</li>
                <li>You become the tenant owner</li>
                <li>After registration, save your tenant ID for future logins</li>
              </ul>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

export default Login
