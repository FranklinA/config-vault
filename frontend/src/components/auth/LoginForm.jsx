import { useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { useAuth } from '../../hooks/useAuth'
import styles from './LoginForm.module.css'

export function LoginForm() {
  const { login, isLoading, error, clearError } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [validationError, setValidationError] = useState(null)

  const from = location.state?.from?.pathname ?? '/projects'

  function validate() {
    if (!email.trim()) return 'El email es requerido.'
    if (!email.includes('@')) return 'El email no es válido.'
    if (!password) return 'La contraseña es requerida.'
    if (password.length < 8) return 'La contraseña debe tener al menos 8 caracteres.'
    return null
  }

  async function handleSubmit(e) {
    e.preventDefault()
    clearError()
    setValidationError(null)

    const msg = validate()
    if (msg) {
      setValidationError(msg)
      return
    }

    try {
      await login(email.trim(), password)
      navigate(from, { replace: true })
    } catch {
      // error already stored in AuthContext
    }
  }

  const displayError = validationError ?? error

  return (
    <div className={styles.page}>
      <div className={styles.card}>
        <div className={styles.logo}>
          <span className={styles.lockIcon}>🔒</span>
          <h1 className={styles.title}>Config Vault</h1>
        </div>

        <form onSubmit={handleSubmit} noValidate className={styles.form}>
          <div className={styles.field}>
            <label htmlFor="email" className={styles.label}>Email</label>
            <input
              id="email"
              type="email"
              className={styles.input}
              value={email}
              onChange={e => { setEmail(e.target.value); setValidationError(null); clearError() }}
              autoComplete="email"
              autoFocus
              disabled={isLoading}
              placeholder="admin@configvault.local"
            />
          </div>

          <div className={styles.field}>
            <label htmlFor="password" className={styles.label}>Password</label>
            <input
              id="password"
              type="password"
              className={styles.input}
              value={password}
              onChange={e => { setPassword(e.target.value); setValidationError(null); clearError() }}
              autoComplete="current-password"
              disabled={isLoading}
            />
          </div>

          {displayError && (
            <div className={styles.error} role="alert">
              <span className={styles.errorIcon}>⚠️</span>
              {displayError}
            </div>
          )}

          <button
            type="submit"
            className={styles.submitButton}
            disabled={isLoading}
          >
            {isLoading ? 'Iniciando sesión…' : 'Login'}
          </button>
        </form>
      </div>
    </div>
  )
}
