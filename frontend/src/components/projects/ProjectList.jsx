import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../../utils/api'
import { usePermissions } from '../../hooks/usePermissions'
import { useNotification } from '../../context/NotificationContext'
import { Modal } from '../common/Modal'
import styles from './ProjectList.module.css'

const ENV_META = {
  development: { label: 'dev', color: 'var(--env-development-text)', icon: '🟢' },
  staging:     { label: 'stg', color: 'var(--env-staging-text)',     icon: '🟡' },
  production:  { label: 'prod', color: 'var(--env-production-text)', icon: '🔴' },
}

export function ProjectList() {
  const [projects, setProjects] = useState([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)

  const { can } = usePermissions()
  const { success, error } = useNotification()
  const navigate = useNavigate()

  useEffect(() => {
    loadProjects()
  }, [])

  async function loadProjects() {
    setLoading(true)
    try {
      const data = await api.get('/api/projects')
      setProjects(data.data ?? data)
    } catch (err) {
      error(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function handleCreate(name, description) {
    try {
      const project = await api.post('/api/projects', { name, description })
      setProjects(prev => [...prev, project])
      setShowCreate(false)
      success('Proyecto creado correctamente.')
    } catch (err) {
      error(err.message)
    }
  }

  return (
    <div className={styles.page}>
      <div className={styles.toolbar}>
        <h1 className={styles.heading}>Projects</h1>
        {can('create', 'projects') && (
          <button className={styles.btnPrimary} onClick={() => setShowCreate(true)}>
            + New Project
          </button>
        )}
      </div>

      {loading ? (
        <div className={styles.empty}>Cargando proyectos…</div>
      ) : projects.length === 0 ? (
        <div className={styles.empty}>No hay proyectos. ¡Crea el primero!</div>
      ) : (
        <div className={styles.grid}>
          {projects.map(project => (
            <ProjectCard
              key={project.id}
              project={project}
              onClick={() => navigate(`/projects/${project.id}`)}
            />
          ))}
        </div>
      )}

      {showCreate && (
        <ProjectModal
          onClose={() => setShowCreate(false)}
          onSave={handleCreate}
        />
      )}
    </div>
  )
}

function ProjectCard({ project, onClick }) {
  const envOrder = ['development', 'staging', 'production']
  const envs = envOrder
    .map(name => project.environments?.find(e => e.name === name))
    .filter(Boolean)

  return (
    <div className={styles.card} onClick={onClick} role="button" tabIndex={0}
      onKeyDown={e => e.key === 'Enter' && onClick()}>
      <div className={styles.cardHeader}>
        <h2 className={styles.cardName}>{project.name}</h2>
        {project.is_archived && <span className={styles.archivedBadge}>Archived</span>}
      </div>
      {project.description && (
        <p className={styles.cardDesc}>{project.description}</p>
      )}
      <div className={styles.envCounts}>
        {envs.map(env => {
          const meta = ENV_META[env.name] ?? {}
          return (
            <span key={env.name} className={styles.envBadge}>
              {meta.icon} {meta.label}: {env.config_count ?? 0}
            </span>
          )
        })}
      </div>
      {project.owner && (
        <p className={styles.cardOwner}>Owner: {project.owner.name}</p>
      )}
    </div>
  )
}

function ProjectModal({ onClose, onSave }) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState(null)

  async function handleSubmit(e) {
    e.preventDefault()
    if (!name.trim()) { setErr('El nombre es requerido.'); return }
    setSaving(true)
    setErr(null)
    try {
      await onSave(name.trim(), description.trim())
    } catch {
      // error handled in parent
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal title="New Project" onClose={onClose}>
      <form onSubmit={handleSubmit} className={styles.form}>
        <div className={styles.field}>
          <label className={styles.label}>Name *</label>
          <input
            className={styles.input}
            value={name}
            onChange={e => { setName(e.target.value); setErr(null) }}
            placeholder="My Application"
            autoFocus
            disabled={saving}
          />
        </div>
        <div className={styles.field}>
          <label className={styles.label}>Description</label>
          <textarea
            className={styles.textarea}
            value={description}
            onChange={e => setDescription(e.target.value)}
            placeholder="Optional description…"
            rows={3}
            disabled={saving}
          />
        </div>
        {err && <p className={styles.fieldError}>{err}</p>}
        <div className={styles.formActions}>
          <button type="button" className={styles.btnSecondary} onClick={onClose} disabled={saving}>
            Cancel
          </button>
          <button type="submit" className={styles.btnPrimary} disabled={saving}>
            {saving ? 'Creating…' : 'Create Project'}
          </button>
        </div>
      </form>
    </Modal>
  )
}
