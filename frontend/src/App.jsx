import React, { useState, useEffect, createContext, useContext } from 'react'
import { BrowserRouter, Routes, Route, Navigate, useNavigate } from 'react-router-dom'
import { ThemeProvider, CssBaseline } from '@mui/material'
import axios from 'axios'

import theme from './theme'
import Layout from './components/Layout'

// Pages
import Dashboard from './pages/Dashboard'
import Login from './pages/Login'
import Register from './pages/Register'
import Predictions from './pages/Predictions'
import Rankings from './pages/Rankings'
import Groups from './pages/Groups'
import GroupDetails from './pages/GroupDetails'
import Profile from './pages/Profile'
import AdminPanel from './pages/AdminPanel'
import Rules from './pages/Rules'
import Auditoria from './pages/Auditoria'

// Auth Context
const AuthContext = createContext(null)

export const useAuth = () => useContext(AuthContext)

// Configure Axios
axios.defaults.baseURL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

function AppContent() {
  const { token, logout } = useAuth()
  const navigate = useNavigate()

  // Setup Axios interceptors
  useEffect(() => {
    const requestInterceptor = axios.interceptors.request.use(
      (config) => {
        const activeToken = localStorage.getItem('token')
        if (activeToken) {
          config.headers.Authorization = `Bearer ${activeToken}`
        }
        return config
      },
      (error) => Promise.reject(error)
    )

    const responseInterceptor = axios.interceptors.response.use(
      (response) => response,
      (error) => {
        if (error.response && error.response.status === 401) {
          const isLoginRequest = error.config && error.config.url && error.config.url.includes('/api/auth/login')
          if (!isLoginRequest) {
            logout()
            navigate('/login')
          }
        }
        return Promise.reject(error)
      }
    )

    return () => {
      axios.interceptors.request.eject(requestInterceptor)
      axios.interceptors.response.eject(responseInterceptor)
    }
  }, [logout, navigate])

  return (
    <Routes>
      {/* Public Auth Routes */}
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />

      {/* Protected Layout Routes */}
      <Route path="/" element={<ProtectedRoute><Layout /></ProtectedRoute>}>
        <Route index element={<Dashboard />} />
        <Route path="predictions" element={<Predictions />} />
        <Route path="rankings" element={<Rankings />} />
        <Route path="groups" element={<Groups />} />
        <Route path="groups/:groupId" element={<GroupDetails />} />
        <Route path="profile" element={<Profile />} />
        <Route path="rules" element={<Rules />} />
        <Route path="audit" element={<Auditoria />} />
        
        {/* Admin Guarded Routes */}
        <Route path="admin" element={
          <AdminProtectedRoute>
            <AdminPanel />
          </AdminProtectedRoute>
        } />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

// Protected Route Guard
function ProtectedRoute({ children }) {
  const { user, loading } = useAuth()

  if (loading) return null // Or a loading spinner

  if (!user) {
    return <Navigate to="/login" replace />
  }

  return children
}

// Admin Route Guard
function AdminProtectedRoute({ children }) {
  const { user, loading } = useAuth()

  if (loading) return null

  if (!user || (user.role !== 'system_admin' && user.role !== 'score_admin')) {
    return <Navigate to="/" replace />
  }

  return children
}

export default function App() {
  const [token, setTokenState] = useState(localStorage.getItem('token'))
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  const setToken = (newToken) => {
    if (newToken) {
      localStorage.setItem('token', newToken)
      setLoading(true)
      setTokenState(newToken)
    } else {
      localStorage.removeItem('token')
      setTokenState(null)
      setUser(null)
      setLoading(false)
    }
  }

  const logout = () => {
    setToken(null)
  }

  // Load user profile on token change
  useEffect(() => {
    const loadUser = async () => {
      if (!token) {
        setUser(null)
        setLoading(false)
        return
      }
      setLoading(true)
      try {
        const res = await axios.get('/api/auth/me', {
          headers: { Authorization: `Bearer ${token}` }
        })
        setUser(res.data)
      } catch (err) {
        logout()
      } finally {
        setLoading(false)
      }
    }
    loadUser()
  }, [token])

  const refreshUser = async () => {
    if (!token) return
    try {
      const res = await axios.get('/api/auth/me')
      setUser(res.data)
    } catch (err) {
      logger.error("Falha ao recarregar dados do usuário")
    }
  }

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <AuthContext.Provider value={{ token, setToken, user, loading, logout, refreshUser }}>
        <BrowserRouter>
          <AppContent />
        </BrowserRouter>
      </AuthContext.Provider>
    </ThemeProvider>
  )
}
