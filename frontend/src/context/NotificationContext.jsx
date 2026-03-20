import { createContext, useContext, useReducer, useCallback } from 'react'
import styles from './NotificationContext.module.css'

const NotificationContext = createContext(null)

let _nextId = 1

const ICONS = {
  success: '✅',
  error:   '❌',
  warning: '⚠️',
  info:    'ℹ️',
}

function notifReducer(state, action) {
  switch (action.type) {
    case 'ADD':    return [...state, action.notification]
    case 'REMOVE': return state.filter(n => n.id !== action.id)
    default:       return state
  }
}

export function NotificationProvider({ children }) {
  const [notifications, dispatch] = useReducer(notifReducer, [])

  const show = useCallback((message, type = 'info', duration = 4000) => {
    const id = _nextId++
    dispatch({ type: 'ADD', notification: { id, message, type } })
    if (duration > 0) {
      setTimeout(() => dispatch({ type: 'REMOVE', id }), duration)
    }
    return id
  }, [])

  const remove = useCallback((id) => dispatch({ type: 'REMOVE', id }), [])

  const value = {
    notifications,
    success: (msg, dur) => show(msg, 'success', dur),
    error:   (msg, dur) => show(msg, 'error',   dur),
    warn:    (msg, dur) => show(msg, 'warning',  dur),
    info:    (msg, dur) => show(msg, 'info',     dur),
    remove,
  }

  return (
    <NotificationContext.Provider value={value}>
      {children}
      <ToastContainer notifications={notifications} onRemove={remove} />
    </NotificationContext.Provider>
  )
}

export function useNotification() {
  const ctx = useContext(NotificationContext)
  if (!ctx) throw new Error('useNotification must be used within NotificationProvider')
  return ctx
}

// ─── Toast renderer ───────────────────────────────────────────────────────────

function ToastContainer({ notifications, onRemove }) {
  if (!notifications.length) return null
  return (
    <div className={styles.container}>
      {notifications.map(n => (
        <Toast key={n.id} notification={n} onRemove={onRemove} />
      ))}
    </div>
  )
}

function Toast({ notification: n, onRemove }) {
  return (
    <div
      className={`${styles.toast} ${styles[n.type]}`}
      onClick={() => onRemove(n.id)}
      role="alert"
    >
      <span className={styles.icon}>{ICONS[n.type]}</span>
      <span className={styles.message}>{n.message}</span>
      <button
        className={styles.close}
        onClick={e => { e.stopPropagation(); onRemove(n.id) }}
        aria-label="Dismiss"
      >
        ✕
      </button>
    </div>
  )
}
