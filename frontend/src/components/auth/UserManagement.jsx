import { useState, useEffect } from 'react'
import { api } from '../../utils/api'
import { useAuth } from '../../hooks/useAuth'
import { useNotification } from '../../context/NotificationContext'
import { Modal } from '../common/Modal'
import styles from './UserManagement.module.css'

const ROLES = ['admin', 'editor', 'viewer']

const ROLE_META = {
  admin:  { icon: '🛡️', cls: 'admin'  },
  editor: { icon: '✏️', cls: 'editor' },
  viewer: { icon: '👁',  cls: 'viewer' },
}

export function UserManagement() {
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)

  const { user: me } = useAuth()
  const { success, error } = useNotification()

  useEffect(() => { load() }, [])

  async function load() {
    setLoading(true)
    try {
      const data = await api.get('/api/users')
      setUsers(data.data ?? data)
    } catch (err) {
      error(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function handleCreate(body) {
    const user = await api.post('/api/users', body)
    setUsers(prev => [...prev, user])
    setShowCreate(false)
    success(`Usuario "${user.name}" creado.`)
  }

  async function handleRoleChange(userId, newRole) {
    try {
      const updated = await api.put(`/api/users/${userId}`, { role: newRole })
      setUsers(prev => prev.map(u => u.id === userId ? updated : u))
      success('Rol actualizado.')
    } catch (err) {
      error(err.message)
    }
  }

  async function handleToggleActive(user) {
    if (user.id === me?.id) {
      error('No puedes desactivarte a ti mismo.')
      return
    }
    try {
      const updated = await api.put(`/api/users/${user.id}`, { is_active: !user.is_active })
      setUsers(prev => prev.map(u => u.id === user.id ? updated : u))
      success(`Usuario ${updated.is_active ? 'activado' : 'desactivado'}.`)
    } catch (err) {
      error(err.message)
    }
  }

  return (
    <div className={styles.page}>
      <div className={styles.toolbar}>
        <h1 className={styles.heading}>Users</h1>
        <button className={styles.btnPrimary} onClick={() => setShowCreate(true)}>
          + Create User
        </button>
      </div>

      {loading ? (
        <div className={styles.empty}>Cargando usuarios…</div>
      ) : (
        <div className={styles.tableWrapper}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th className={styles.th}>Name</th>
                <th className={styles.th}>Email</th>
                <th className={styles.th}>Role</th>
                <th className={styles.th}>Status</th>
                <th className={styles.th}>Created</th>
              </tr>
            </thead>
            <tbody>
              {users.map(user => (
                <UserRow
                  key={user.id}
                  user={user}
                  isSelf={user.id === me?.id}
                  onRoleChange={handleRoleChange}
                  onToggleActive={handleToggleActive}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showCreate && (
        <CreateUserModal
          onClose={() => setShowCreate(false)}
          onSave={handleCreate}
        />
      )}
    </div>
  )
}

// ─── Row ──────────────────────────────────────────────────────────────────────

function UserRow({ user, isSelf, onRoleChange, onToggleActive }) {
  const meta = ROLE_META[user.role] ?? { icon: '?', cls: 'viewer' }

  return (
    <tr className={`${styles.row} ${!user.is_active ? styles.inactive : ''}`}>
      <td className={styles.td}>
        <span className={styles.userName}>{user.name}</span>
        {isSelf && <span className={styles.selfBadge}>You</span>}
      </td>
      <td className={styles.td}>
        <span className={styles.email}>{user.email}</span>
      </td>
      <td className={styles.td}>
        <select
          className={`${styles.roleSelect} ${styles[meta.cls]}`}
          value={user.role}
          onChange={e => onRoleChange(user.id, e.target.value)}
          disabled={isSelf}
        >
          {ROLES.map(r => (
            <option key={r} value={r}>
              {ROLE_META[r].icon} {r}
            </option>
          ))}
        </select>
      </td>
      <td className={styles.td}>
        <button
          className={`${styles.statusBtn} ${user.is_active ? styles.active : styles.deactive}`}
          onClick={() => onToggleActive(user)}
          disabled={isSelf}
          title={isSelf ? 'No puedes desactivarte a ti mismo' : ''}
        >
          {user.is_active ? '● Active' : '○ Inactive'}
        </button>
      </td>
      <td className={styles.td}>
        <span className={styles.date}>
          {new Date(user.created_at).toLocaleDateString()}
        </span>
      </td>
    </tr>
  )
}

// ─── Create Modal ─────────────────────────────────────────────────────────────

function CreateUserModal({ onClose, onSave }) {
  const [form, setForm] = useState({ name: '', email: '', password: '', role: 'editor' })
  const [errors, setErrors] = useState({})
  const [saving, setSaving] = useState(false)
  const { error } = useNotification()

  function set(key, val) {
    setForm(p => ({ ...p, [key]: val }))
    setErrors(p => ({ ...p, [key]: null }))
  }

  function validate() {
    const e = {}
    if (!form.name.trim())  e.name  = 'Requerido.'
    if (!form.email.trim()) e.email = 'Requerido.'
    if (!form.email.includes('@')) e.email = 'Email inválido.'
    if (form.password.length < 8) e.password = 'Mínimo 8 caracteres.'
    return e
  }

  async function handleSubmit(evt) {
    evt.preventDefault()
    const errs = validate()
    if (Object.keys(errs).length) { setErrors(errs); return }
    setSaving(true)
    try {
      await onSave({ ...form, name: form.name.trim(), email: form.email.trim() })
    } catch (err) {
      error(err.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal title="Create User" onClose={onClose}>
      <form onSubmit={handleSubmit} className={styles.form}>
        <Field label="Full name *" error={errors.name}>
          <input className={styles.input} value={form.name}
            onChange={e => set('name', e.target.value)} autoFocus disabled={saving} />
        </Field>
        <Field label="Email *" error={errors.email}>
          <input className={styles.input} type="email" value={form.email}
            onChange={e => set('email', e.target.value)} disabled={saving} />
        </Field>
        <Field label="Password *" error={errors.password}>
          <input className={styles.input} type="password" value={form.password}
            onChange={e => set('password', e.target.value)} disabled={saving}
            autoComplete="new-password" />
        </Field>
        <Field label="Role">
          <select className={styles.input} value={form.role}
            onChange={e => set('role', e.target.value)} disabled={saving}>
            {ROLES.map(r => <option key={r} value={r}>{r}</option>)}
          </select>
        </Field>

        <div className={styles.formActions}>
          <button type="button" className={styles.btnSecondary} onClick={onClose} disabled={saving}>
            Cancel
          </button>
          <button type="submit" className={styles.btnPrimary} disabled={saving}>
            {saving ? 'Creating…' : 'Create User'}
          </button>
        </div>
      </form>
    </Modal>
  )
}

function Field({ label, error, children }) {
  return (
    <div className={styles.field}>
      <label className={styles.label}>{label}</label>
      {children}
      {error && <span className={styles.err}>{error}</span>}
    </div>
  )
}
