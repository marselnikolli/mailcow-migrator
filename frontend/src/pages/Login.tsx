import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { authApi } from '../api'

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

      // Store token and tenant info
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

      // Store token and tenant info
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
    <div className="min-h-screen bg-gradient-to-br from-blue-600 to-blue-800 flex items-center justify-center px-4 sm:px-6 lg:px-8">
      <div className="bg-white rounded-lg shadow-xl p-8 max-w-md w-full">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-gray-900">📧 mailcow-migrator</h1>
          <p className="text-gray-600 mt-2">Mail Migration as a Service</p>
        </div>

        {error && <div className="mb-6 p-4 bg-red-100 text-red-800 rounded-lg text-sm">{error}</div>}

        <form onSubmit={isRegister ? handleRegister : handleLogin} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="you@example.com"
              required
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="••••••••"
              required
            />
          </div>

          {isRegister && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Tenant Name</label>
              <input
                type="text"
                value={tenantName}
                onChange={(e) => setTenantName(e.target.value)}
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="My Company"
                required
              />
            </div>
          )}

          {!isRegister && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Tenant ID</label>
              <input
                type="number"
                value={tenantId}
                onChange={(e) => setTenantId(e.target.value)}
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="1"
                required
              />
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-blue-600 text-white py-2 rounded-lg hover:bg-blue-700 font-medium disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? 'Loading...' : isRegister ? 'Create Account' : 'Login'}
          </button>
        </form>

        <div className="mt-6 text-center">
          <p className="text-gray-600">
            {isRegister ? 'Already have an account?' : "Don't have an account?"}
            <button
              type="button"
              onClick={() => setIsRegister(!isRegister)}
              className="text-blue-600 hover:text-blue-700 font-medium ml-2"
            >
              {isRegister ? 'Login' : 'Register'}
            </button>
          </p>
        </div>

        {isRegister && (
          <div className="mt-6 p-4 bg-blue-50 border border-blue-200 rounded-lg text-sm text-blue-800">
            <p className="font-medium mb-2">✓ Creating a new account:</p>
            <ul className="list-disc list-inside space-y-1 text-xs">
              <li>Creates a new tenant (organization)</li>
              <li>You become the tenant owner</li>
              <li>After registration, save your tenant ID for future logins</li>
            </ul>
          </div>
        )}
      </div>
    </div>
  )
}

export default Login
