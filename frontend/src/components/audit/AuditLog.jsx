import { useState, useEffect, useCallback } from 'react'
import { api, getToken } from '../../utils/api'
import { useNotification } from '../../context/NotificationContext'
import { AuditEntry } from './AuditEntry'
import styles from './AuditLog.module.css'

const ALL_ACTIONS = [
  'login', 'logout', 'login_failed',
  'user_created', 'user_updated',
  'project_created', 'project_updated', 'project_deleted',
  'config_created', 'config_updated', 'config_deleted',
  'approval_requested', 'approval_approved', 'approval_rejected', 'approval_cancelled',
  'secret_accessed',
]

const PER_PAGE = 20

export function AuditLog() {
  const [entries, setEntries] = useState([])
  const [pagination, setPagination] = useState(null)
  const [loading, setLoading] = useState(true)
  const [exporting, setExporting] = useState(false)

  // filter state
  const [action, setAction]     = useState('')
  const [userId, setUserId]     = useState('')
  const [projectId, setProjectId] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo]     = useState('')
  const [page, setPage]         = useState(1)

  // lookup data for dropdowns
  const [users, setUsers]       = useState([])
  const [projects, setProjects] = useState([])

  const { error, success } = useNotification()

  // Load dropdown data once
  useEffect(() => {
    api.get('/api/users').then(d => setUsers(d.data ?? d)).catch(() => {})
    api.get('/api/projects').then(d => setProjects(d.data ?? d)).catch(() => {})
  }, [])

  const buildParams = useCallback(() => {
    const p = new URLSearchParams()
    p.set('page', page)
    p.set('per_page', PER_PAGE)
    if (action)    p.set('action', action)
    if (userId)    p.set('user_id', userId)
    if (projectId) p.set('project_id', projectId)
    if (dateFrom)  p.set('date_from', dateFrom)
    if (dateTo)    p.set('date_to', dateTo)
    return p
  }, [action, userId, projectId, dateFrom, dateTo, page])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await api.get(`/api/audit?${buildParams()}`)
      setEntries(data.data ?? data)
      setPagination(data.pagination ?? null)
    } catch (err) {
      error(err.message)
    } finally {
      setLoading(false)
    }
  }, [buildParams])

  useEffect(() => { load() }, [load])

  // Reset to page 1 when filters change
  useEffect(() => { setPage(1) }, [action, userId, projectId, dateFrom, dateTo])

  async function handleExport() {
    setExporting(true)
    try {
      const params = buildParams()
      params.delete('page')
      params.delete('per_page')

      const response = await fetch(`/api/audit/export?${params}`, {
        headers: { 'Authorization': `Bearer ${getToken()}` },
      })
      if (!response.ok) throw new Error('Export failed')

      const blob = await response.blob()
      const url  = URL.createObjectURL(blob)
      const a    = document.createElement('a')
      a.href     = url
      a.download = `audit-log-${new Date().toISOString().split('T')[0]}.csv`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
      success('CSV exportado.')
    } catch (err) {
      error(err.message)
    } finally {
      setExporting(false)
    }
  }

  const totalPages = pagination?.pages ?? 1

  return (
    <div className={styles.page}>
      {/* ── Toolbar ── */}
      <div className={styles.toolbar}>
        <h1 className={styles.heading}>Audit Log</h1>
        <button
          className={styles.btnExport}
          onClick={handleExport}
          disabled={exporting}
        >
          {exporting ? 'Exporting…' : '⬇ Export CSV'}
        </button>
      </div>

      {/* ── Filters ── */}
      <div className={styles.filters}>
        <div className={styles.filterGroup}>
          <label className={styles.filterLabel}>Action</label>
          <select className={styles.select} value={action} onChange={e => setAction(e.target.value)}>
            <option value="">All</option>
            {ALL_ACTIONS.map(a => <option key={a} value={a}>{a}</option>)}
          </select>
        </div>

        <div className={styles.filterGroup}>
          <label className={styles.filterLabel}>User</label>
          <select className={styles.select} value={userId} onChange={e => setUserId(e.target.value)}>
            <option value="">All</option>
            {users.map(u => <option key={u.id} value={u.id}>{u.name}</option>)}
          </select>
        </div>

        <div className={styles.filterGroup}>
          <label className={styles.filterLabel}>Project</label>
          <select className={styles.select} value={projectId} onChange={e => setProjectId(e.target.value)}>
            <option value="">All</option>
            {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </div>

        <div className={styles.filterGroup}>
          <label className={styles.filterLabel}>From</label>
          <input
            type="date"
            className={styles.dateInput}
            value={dateFrom}
            onChange={e => setDateFrom(e.target.value)}
          />
        </div>

        <div className={styles.filterGroup}>
          <label className={styles.filterLabel}>To</label>
          <input
            type="date"
            className={styles.dateInput}
            value={dateTo}
            onChange={e => setDateTo(e.target.value)}
          />
        </div>

        {(action || userId || projectId || dateFrom || dateTo) && (
          <button className={styles.clearBtn} onClick={() => {
            setAction(''); setUserId(''); setProjectId(''); setDateFrom(''); setDateTo('')
          }}>
            Clear
          </button>
        )}
      </div>

      {/* ── Entries ── */}
      {loading ? (
        <div className={styles.empty}>Cargando registros…</div>
      ) : entries.length === 0 ? (
        <div className={styles.empty}>No hay registros con los filtros aplicados.</div>
      ) : (
        <div className={styles.logCard}>
          {entries.map(entry => (
            <AuditEntry key={entry.id} entry={entry} />
          ))}
        </div>
      )}

      {/* ── Pagination ── */}
      {totalPages > 1 && (
        <div className={styles.pagination}>
          <button
            className={styles.pageBtn}
            onClick={() => setPage(p => Math.max(1, p - 1))}
            disabled={page === 1 || loading}
          >
            ← Previous
          </button>
          <span className={styles.pageInfo}>
            Page {page} of {totalPages}
            {pagination?.total != null && (
              <span className={styles.total}> ({pagination.total} entries)</span>
            )}
          </span>
          <button
            className={styles.pageBtn}
            onClick={() => setPage(p => Math.min(totalPages, p + 1))}
            disabled={page === totalPages || loading}
          >
            Next →
          </button>
        </div>
      )}
    </div>
  )
}
