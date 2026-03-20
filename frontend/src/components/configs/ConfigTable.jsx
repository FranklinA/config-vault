import { useState, useEffect, useCallback } from 'react'
import { api } from '../../utils/api'
import { usePermissions } from '../../hooks/usePermissions'
import { useNotification } from '../../context/NotificationContext'
import { SecretField } from './SecretField'
import { FeatureFlagToggle } from './FeatureFlagToggle'
import { ConfigEditor } from './ConfigEditor'
import styles from './ConfigTable.module.css'

// ─── Type metadata ─────────────────────────────────────────────────────────────

const TYPE_META = {
  string:       { icon: 'Aa', label: 'string',       cls: 'typeString'  },
  number:       { icon: '#',  label: 'number',        cls: 'typeNumber'  },
  boolean:      { icon: '⊘',  label: 'boolean',       cls: 'typeBoolean' },
  json:         { icon: '{}', label: 'json',          cls: 'typeJson'    },
  secret:       { icon: '🔒', label: 'secret',        cls: 'typeSecret'  },
  feature_flag: { icon: '🚩', label: 'feature_flag',  cls: 'typeFlag'    },
}

// ─── Helpers ───────────────────────────────────────────────────────────────────

function truncate(str, n = 60) {
  if (!str) return '—'
  return str.length > n ? str.slice(0, n) + '…' : str
}

function canDeleteInEnv(role, envName) {
  if (role === 'admin') return true
  if (role === 'editor') return envName !== 'production'
  return false
}

// ─── Component ─────────────────────────────────────────────────────────────────

/**
 * @param {number} projectId
 * @param {object} env  - { id, name, require_approval }
 */
export function ConfigTable({ projectId, env }) {
  const [configs, setConfigs] = useState([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [editorState, setEditorState] = useState(null)  // null | { config: null|obj }
  const [deletingId, setDeletingId] = useState(null)

  const { can, role } = usePermissions()
  const { success, error } = useNotification()

  const canEdit   = can('edit', 'configs')
  const canCreate = can('create', 'configs')
  const canReveal = can('view_secret', 'configs')
  const canDeleteHere = canDeleteInEnv(role, env.name)

  const loadConfigs = useCallback(async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams()
      if (search) params.set('search', search)
      const data = await api.get(
        `/api/projects/${projectId}/environments/${env.id}/configs?${params}`
      )
      setConfigs(Array.isArray(data) ? data : (data.data ?? []))
    } catch (err) {
      error(err.message)
    } finally {
      setLoading(false)
    }
  }, [projectId, env.id, search])

  useEffect(() => { loadConfigs() }, [loadConfigs])

  // Debounce search
  useEffect(() => {
    const t = setTimeout(loadConfigs, 300)
    return () => clearTimeout(t)
  }, [search])

  async function handleDelete(config) {
    setDeletingId(config.id)
    try {
      await api.delete(
        `/api/projects/${projectId}/environments/${env.id}/configs/${config.id}`
      )
      setConfigs(prev => prev.filter(c => c.id !== config.id))
      success(`"${config.key}" eliminado.`)
    } catch (err) {
      error(err.message)
    } finally {
      setDeletingId(null)
    }
  }

  function handleSaved(result) {
    if (!result || result.approvalCreated) {
      // Approval was created or no direct config returned — refresh
      loadConfigs()
      return
    }
    setConfigs(prev => {
      const idx = prev.findIndex(c => c.id === result.id)
      if (idx >= 0) {
        const next = [...prev]
        next[idx] = result
        return next
      }
      return [...prev, result]
    })
  }

  function handleToggleChange(configId, updatedConfig) {
    if (!updatedConfig) { loadConfigs(); return }
    setConfigs(prev => prev.map(c => c.id === configId ? updatedConfig : c))
  }

  const filtered = configs.filter(c =>
    !search ||
    c.key.toLowerCase().includes(search.toLowerCase()) ||
    (c.description ?? '').toLowerCase().includes(search.toLowerCase())
  )

  return (
    <div className={styles.container}>
      <div className={styles.toolbar}>
        {canCreate && (
          <button
            className={styles.btnAdd}
            onClick={() => setEditorState({ config: null })}
          >
            + Add Config
          </button>
        )}
        <div className={styles.searchWrapper}>
          <span className={styles.searchIcon}>🔍</span>
          <input
            className={styles.search}
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search configs…"
          />
        </div>
      </div>

      {loading ? (
        <div className={styles.empty}>Cargando configuraciones…</div>
      ) : filtered.length === 0 ? (
        <div className={styles.empty}>
          {search ? 'Sin resultados.' : 'No hay configuraciones en este ambiente.'}
        </div>
      ) : (
        <div className={styles.tableWrapper}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th className={styles.th}>Key</th>
                <th className={styles.th}>Type</th>
                <th className={styles.th}>Value</th>
                <th className={`${styles.th} ${styles.actionsCol}`}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map(config => (
                <ConfigRow
                  key={config.id}
                  config={config}
                  projectId={projectId}
                  env={env}
                  canEdit={canEdit}
                  canReveal={canReveal}
                  canDelete={canDeleteHere}
                  isDeleting={deletingId === config.id}
                  onEdit={() => setEditorState({ config })}
                  onDelete={() => handleDelete(config)}
                  onToggleChange={updated => handleToggleChange(config.id, updated)}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {editorState && (
        <ConfigEditor
          config={editorState.config}
          projectId={projectId}
          env={env}
          onClose={() => setEditorState(null)}
          onSaved={handleSaved}
        />
      )}
    </div>
  )
}

// ─── Row ───────────────────────────────────────────────────────────────────────

function ConfigRow({ config, projectId, env, canEdit, canReveal, canDelete, isDeleting, onEdit, onDelete, onToggleChange }) {
  const meta = TYPE_META[config.config_type] ?? { icon: '?', label: config.config_type, cls: 'typeString' }

  return (
    <tr className={styles.row}>
      <td className={styles.td}>
        <code className={styles.key}>{config.key}</code>
        {config.description && (
          <span className={styles.desc}>{config.description}</span>
        )}
      </td>

      <td className={styles.td}>
        <span className={`${styles.typeBadge} ${styles[meta.cls]}`}>
          <span className={styles.typeIcon}>{meta.icon}</span>
          {meta.label}
        </span>
      </td>

      <td className={styles.td}>
        <ValueCell
          config={config}
          projectId={projectId}
          envId={env.id}
          canReveal={canReveal}
          canEdit={canEdit}
          onToggleChange={onToggleChange}
        />
      </td>

      <td className={`${styles.td} ${styles.actionsCell}`}>
        {canEdit && (
          <button className={styles.iconBtn} onClick={onEdit} title="Edit">
            ✏️
          </button>
        )}
        {canDelete && (
          <button
            className={`${styles.iconBtn} ${styles.deleteBtn}`}
            onClick={onDelete}
            disabled={isDeleting}
            title="Delete"
          >
            🗑
          </button>
        )}
      </td>
    </tr>
  )
}

function ValueCell({ config, projectId, envId, canReveal, canEdit, onToggleChange }) {
  switch (config.config_type) {
    case 'secret':
      return (
        <SecretField
          projectId={projectId}
          envId={envId}
          configId={config.id}
          canReveal={canReveal}
        />
      )

    case 'feature_flag':
      return (
        <FeatureFlagToggle
          value={config.value}
          projectId={projectId}
          envId={envId}
          configId={config.id}
          disabled={!canEdit}
          onChange={onToggleChange}
        />
      )

    case 'boolean':
      return (
        <span className={`${styles.boolValue} ${config.value === 'true' ? styles.boolTrue : styles.boolFalse}`}>
          {config.value === 'true' ? '✓ true' : '✗ false'}
        </span>
      )

    case 'json':
      return (
        <code className={styles.jsonValue} title={config.value}>
          {truncate(config.value, 50)}
        </code>
      )

    default:
      return (
        <span className={styles.strValue} title={config.value}>
          {truncate(config.value)}
        </span>
      )
  }
}
