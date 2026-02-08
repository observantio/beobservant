import { createContext, useContext, useState, useEffect } from 'react'
import PropTypes from 'prop-types'
import * as api from '../api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [token, setToken] = useState(localStorage.getItem('auth_token'))
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (token) {
      api.setAuthToken(token)
      loadUser()
    } else {
      setLoading(false)
    }
  }, [token])

  const loadUser = async () => {
    try {
      const userData = await api.getCurrentUser()
      setUser(userData)
    } catch (error) {
      logout()
    } finally {
      setLoading(false)
    }
  }

  const login = async (username, password) => {
    const response = await api.login(username, password)
    const { access_token } = response
    localStorage.setItem('auth_token', access_token)
    setToken(access_token)
    api.setAuthToken(access_token)
    await loadUser()
    return response
  }

  const register = async (username, email, password, fullName) => {
    const response = await api.register(username, email, password, fullName)
    return response
  }

  const logout = () => {
    localStorage.removeItem('auth_token')
    setToken(null)
    setUser(null)
    api.setAuthToken(null)
  }

  const refreshUser = async () => {
    if (token) {
      try {
        const userData = await api.getCurrentUser()
        setUser(userData)
      } catch (error) {
        console.error('Failed to refresh user:', error)
      }
    }
  }

  const value = {
    user,
    token,
    loading,
    login,
    register,
    logout,
    refreshUser,
    isAuthenticated: !!token && !!user,
    hasPermission: (permission) => user?.permissions?.includes(permission) || false
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

AuthProvider.propTypes = {
  children: PropTypes.node.isRequired
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider')
  }
  return context
}
