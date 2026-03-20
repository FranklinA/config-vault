import { createContext, useContext, useReducer, useEffect, useCallback } from 'react'
import { setToken, clearToken, api } from '../utils/api'

const AuthContext = createContext(null)

const initialState = {
  user: null,      // { id, name, email, role }
  token: null,
  isLoading: false,
  error: null,
}

function authReducer(state, action) {
  switch (action.type) {
    case 'LOGIN_START':
      return { ...state, isLoading: true, error: null }
    case 'LOGIN_SUCCESS':
      return { ...state, isLoading: false, user: action.user, token: action.token, error: null }
    case 'LOGIN_ERROR':
      return { ...state, isLoading: false, error: action.error }
    case 'LOGOUT':
      return { ...initialState }
    case 'CLEAR_ERROR':
      return { ...state, error: null }
    default:
      return state
  }
}

export function AuthProvider({ children }) {
  const [state, dispatch] = useReducer(authReducer, initialState)

  // Listen for 401 events emitted by the fetch wrapper → silent logout
  useEffect(() => {
    function handleUnauthorized() {
      clearToken()
      dispatch({ type: 'LOGOUT' })
    }
    window.addEventListener('auth:unauthorized', handleUnauthorized)
    return () => window.removeEventListener('auth:unauthorized', handleUnauthorized)
  }, [])

  const logout = useCallback(async () => {
    try {
      await api.post('/api/auth/logout')
    } catch {
      // Always clear local state regardless of API response
    }
    clearToken()
    dispatch({ type: 'LOGOUT' })
  }, [])

  async function login(email, password) {
    dispatch({ type: 'LOGIN_START' })
    try {
      const data = await api.post('/api/auth/login', { email, password })
      setToken(data.access_token)
      dispatch({ type: 'LOGIN_SUCCESS', user: data.user, token: data.access_token })
    } catch (err) {
      dispatch({ type: 'LOGIN_ERROR', error: err.message })
      throw err
    }
  }

  const value = {
    user: state.user,
    token: state.token,
    isLoading: state.isLoading,
    error: state.error,
    isAuthenticated: !!state.user,
    login,
    logout,
    clearError: () => dispatch({ type: 'CLEAR_ERROR' }),
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
