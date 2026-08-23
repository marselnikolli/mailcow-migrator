import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom'
import './index.css'

import { ThemeProvider } from './components/theme-provider'
import AppLayout from './components/AppLayout'
import Dashboard from './pages/Dashboard'
import Login from './pages/Login'
import Domains from './pages/Domains'
import Jobs from './pages/Jobs'

const ProtectedRoute: React.FC<{ element: React.ReactElement }> = ({ element }) => {
  const token = localStorage.getItem('token')
  return token ? element : <Navigate to="/login" />
}

const App = () => {
  return (
    <ThemeProvider defaultTheme="system" storageKey="theme">
      <Router>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route
            path="/"
            element={
              <ProtectedRoute
                element={
                  <AppLayout>
                    <Dashboard />
                  </AppLayout>
                }
              />
            }
          />
          <Route
            path="/domains"
            element={
              <ProtectedRoute
                element={
                  <AppLayout>
                    <Domains />
                  </AppLayout>
                }
              />
            }
          />
          <Route
            path="/jobs"
            element={
              <ProtectedRoute
                element={
                  <AppLayout>
                    <Jobs />
                  </AppLayout>
                }
              />
            }
          />
          <Route path="*" element={<Navigate to="/" />} />
        </Routes>
      </Router>
    </ThemeProvider>
  )
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
