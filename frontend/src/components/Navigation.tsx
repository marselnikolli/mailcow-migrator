import React from 'react'
import { Link, useNavigate } from 'react-router-dom'

const Navigation: React.FC = () => {
  const navigate = useNavigate()
  const token = localStorage.getItem('token')
  
  const handleLogout = () => {
    localStorage.removeItem('token')
    localStorage.removeItem('tenant_id')
    localStorage.removeItem('user_id')
    localStorage.removeItem('role')
    navigate('/login')
  }

  if (!token) return null

  return (
    <nav className="bg-blue-600 text-white shadow-lg">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between items-center h-16">
          <Link to="/" className="text-2xl font-bold">
            📧 mailcow-migrator
          </Link>
          
          <div className="flex gap-6 items-center">
            <Link to="/" className="hover:text-blue-100 font-medium">Dashboard</Link>
            <Link to="/domains" className="hover:text-blue-100 font-medium">Domains</Link>
            <Link to="/jobs" className="hover:text-blue-100 font-medium">Jobs</Link>
            
            <button
              onClick={handleLogout}
              className="px-4 py-2 bg-red-500 hover:bg-red-600 rounded-lg font-medium"
            >
              Logout
            </button>
          </div>
        </div>
      </div>
    </nav>
  )
}

export default Navigation
