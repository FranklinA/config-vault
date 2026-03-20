import { createContext, useContext, useReducer, useCallback } from 'react'

const NotificationContext = createContext(null)

let _nextId = 1

function notifReducer(state, action) {
  switch (action.type) {
    case 'ADD':
      return [...state, action.notification]
    case 'REMOVE':
      return state.filter(n => n.id !== action.id)
    default:
      return state
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

// ─── Inline toast renderer ────────────────────────────────────────────────────

const TYPE_STYLES = {
  success: { background: 'var(--color-success)',       color: '#fff' },
  error:   { background: 'var(--color-danger)',         color: '#fff' },
  warning: { background: 'var(--color-warning)',        color: '#fff' },
  info:    { background: 'var(--color-primary)',        color: '#fff' },
}

function ToastContainer({ notifications, onRemove }) {
  if (!notifications.length) return null

  return (
    <div style={{
      position: 'fixed',
      bottom: '24px',
      right: '24px',
      display: 'flex',
      flexDirection: 'column',
      gap: '8px',
      zIndex: 9999,
      maxWidth: '360px',
    }}>
      {notifications.map(n => (
        <div
          key={n.id}
          onClick={() => onRemove(n.id)}
          style={{
            ...TYPE_STYLES[n.type],
            padding: '12px 16px',
            borderRadius: 'var(--radius-md)',
            boxShadow: 'var(--shadow-lg)',
            cursor: 'pointer',
            fontSize: '0.875rem',
            lineHeight: '1.4',
          }}
        >
          {n.message}
        </div>
      ))}
    </div>
  )
}
