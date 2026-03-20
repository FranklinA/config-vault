import { useState, useEffect } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { api } from '../../utils/api'
import { usePermissions } from '../../hooks/usePermissions'
import { useAuth } from '../../hooks/useAuth'
import { useNotification } from '../../context/NotificationContext'
import { EnvironmentTabs } from './EnvironmentTabs'
import { ConfigTable } from '../configs/ConfigTable'
import { Modal } from '../common/Modal'
import styles from './ProjectDetail.module.css'

export function ProjectDetail() {
  const { projectId } = useParams()
  const navigate = useNavigate()
  const { can, role } = usePermissions()
  const { user } = useAuth()
  const { success, error } = useNotification()

  const [project, setProject] = useState(null)
  const [activeEnv, setActiveEnv] = useState(null)
  const [loading, setLoading] = useState(true)
  const [showEdit, setShowEdit] = useState(false)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)

  useEffect(() => {
    loadProject()
  }, [projectId])

  async function loadProject() {
    setLoading(true)
    try {
      const data = await api.get(`/api/projects/${projectId}`)
      setProject(data)
      // default to first env (development)
      if (data.environments?.length) {
        setActiveEnv(data.environments.find(e => e.name === 'development') ?? data.environments[0])
      }
    } catch (err) {
      error(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function handleEdit(name, description) {
    try {
      const updated = await api.put(`/api/projects/${projectId}`, { name, description })
      setProject(updated)
      setShowEdit(false)
      success('Proyecto actualizado.')
    } catch (err) {
      error(err.message)
      throw err
    }
  }

  async function handleDelete() {
    try {
      await api.delete(`/api/projects/${projectId}`)
      success('Proyecto eliminado.')
      navigate('/projects')
    } catch (err) {
      error(err.message)
    }
  }

  const canEdit = can('edit', 'projects') &&
    (role === 'admin' || project?.owner?.id === user?.id)
  const canDelete = can('delete', 'projects')

  if (loading) return <div className={styles.loading}>Cargando proyecto…</div>
  if (!project) return <div className={styles.loading}>Proyecto no encontrado.</div>

  return (
    <div className={styles.page}>
      <Link to="/projects" className={styles.backLink}>← Projects</Link>

      <div className={styles.header}>
        <div>
          <h1 className={styles.projectName}>{project.name}</h1>
          {project.description && (
            <p className={styles.projectDesc}>{project.description}</p>
          )}
          {project.owner && (
            <p className={styles.owner}>Owner: {project.owner.name}</p>
          )}
        </div>
        <div className={styles.headerActions}>
          {canEdit && (
            <button className={styles.btnSecondary} onClick={() => setShowEdit(true)}>
              Edit
            </button>
          )}
          {canDelete && (
            <button className={styles.btnDanger} onClick={() => setShowDeleteConfirm(true)}>
              Delete
            </button>
          )}
        </div>
      </div>

      {activeEnv && (
        <>
          <EnvironmentTabs
            environments={project.environments}
            activeEnvId={activeEnv.id}
            onSelect={setActiveEnv}
          />
          <ConfigTable
            projectId={project.id}
            env={activeEnv}
          />
        </>
      )}

      {showEdit && (
        <ProjectEditModal
          project={project}
          onClose={() => setShowEdit(false)}
          onSave={handleEdit}
        />
      )}

      {showDeleteConfirm && (
        <Modal title="Delete Project" onClose={() => setShowDeleteConfirm(false)} size="sm">
          <p className={styles.confirmText}>
            ¿Eliminar el proyecto <strong>{project.name}</strong>? Esta acción es irreversible
            y eliminará todos los environments, configuraciones y aprobaciones asociadas.
          </p>
          <div className={styles.confirmActions}>
            <button className={styles.btnSecondary} onClick={() => setShowDeleteConfirm(false)}>
              Cancel
            </button>
            <button className={styles.btnDanger} onClick={handleDelete}>
              Delete
            </button>
          </div>
        </Modal>
      )}
    </div>
  )
}

function ProjectEditModal({ project, onClose, onSave }) {
  const [name, setName] = useState(project.name)
  const [description, setDescription] = useState(project.description ?? '')
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
      setErr('No se pudo actualizar el proyecto.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal title="Edit Project" onClose={onClose}>
      <form onSubmit={handleSubmit} className={styles.form}>
        <div className={styles.field}>
          <label className={styles.label}>Name *</label>
          <input
            className={styles.input}
            value={name}
            onChange={e => { setName(e.target.value); setErr(null) }}
            disabled={saving}
            autoFocus
          />
        </div>
        <div className={styles.field}>
          <label className={styles.label}>Description</label>
          <textarea
            className={styles.textarea}
            value={description}
            onChange={e => setDescription(e.target.value)}
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
            {saving ? 'Saving…' : 'Save Changes'}
          </button>
        </div>
      </form>
    </Modal>
  )
}
