import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../../utils/api'
import { useAuth } from '../../hooks/useAuth'
import { useNotification } from '../../context/NotificationContext'
import { ApprovalActions } from './ApprovalActions'
import styles from './ApprovalList.module.css'

// ─── Helpers ───────────────────────────────────────────────────────────────────

export const STATUS_META = {
  pending:   { label: 'PENDING',   cls: 'pending',   icon: '🟡' },
  approved:  { label: 'APPROVED',  cls: 'approved',  icon: '✅' },
  rejected:  { label: 'REJECTED',  cls: 'rejected',  icon: '❌' },
  cancelled: { label: 'CANCELLED', cls: 'cancelled', icon: '⊘'  },
}

export const ACTION_LABELS = {
  create: 'Create config',
  update: 'Update config',
  delete: 'Delete config',
}

export function formatRelativeTime(dateStr) {
  const diff = Date.now() - new Date(dateStr).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins} min ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

const STATUS_OPTIONS = ['all', 'pending', 'approved', 'rejected', 'cancelled']

// ─── Component ─────────────────────────────────────────────────────────────────

export function ApprovalList() {
  const [approvals, setApprovals] = useState([])
  const [statusFilter, setStatusFilter] = useState('pending')
  const [loading, setLoading] = useState(true)

  const { user } = useAuth()
  const { error } = useNotification()
  const navigate = useNavigate()

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams()
      if (statusFilter !== 'all') params.set('status', statusFilter)
      const data = await api.get(`/api/approvals?${params}`)
      setApprovals(data.data ?? data)
    } catch (err) {
      error(err.message)
    } finally {
      setLoading(false)
    }
  }, [statusFilter])

  useEffect(() => { load() }, [load])

  function handleActionDone(updatedApproval) {
    setApprovals(prev =>
      prev.map(a => a.id === updatedApproval.id ? updatedApproval : a)
    )
  }

  return (
    <div className={styles.page}>
      <div className={styles.toolbar}>
        <h1 className={styles.heading}>Approvals</h1>
        <div className={styles.filterGroup}>
          <label className={styles.filterLabel}>Status:</label>
          <select
            className={styles.select}
            value={statusFilter}
            onChange={e => setStatusFilter(e.target.value)}
          >
            {STATUS_OPTIONS.map(s => (
              <option key={s} value={s}>
                {s.charAt(0).toUpperCase() + s.slice(1)}
              </option>
            ))}
          </select>
        </div>
      </div>

      {loading ? (
        <div className={styles.empty}>Cargando solicitudes…</div>
      ) : approvals.length === 0 ? (
        <div className={styles.empty}>
          No hay solicitudes{statusFilter !== 'all' ? ` con estado "${statusFilter}"` : ''}.
        </div>
      ) : (
        <div className={styles.list}>
          {approvals.map(approval => (
            <ApprovalCard
              key={approval.id}
              approval={approval}
              currentUserId={user?.id}
              onActionDone={handleActionDone}
              onViewDetail={() => navigate(`/approvals/${approval.id}`)}
            />
          ))}
        </div>
      )}
    </div>
  )
}

// ─── Card ──────────────────────────────────────────────────────────────────────

function ApprovalCard({ approval, onActionDone, onViewDetail }) {
  const meta = STATUS_META[approval.status] ?? STATUS_META.pending

  return (
    <div className={`${styles.card} ${styles[`border_${meta.cls}`]}`}>
      <div className={styles.cardTop}>
        <div className={styles.cardLeft}>
          <span className={`${styles.statusBadge} ${styles[meta.cls]}`}>
            {meta.icon} {meta.label}
          </span>
          <span className={styles.actionLabel}>
            {ACTION_LABELS[approval.action] ?? approval.action}
          </span>
          <code className={styles.keyLabel}>{approval.key}</code>
        </div>
        <button className={styles.detailLink} onClick={onViewDetail}>
          View →
        </button>
      </div>

      <div className={styles.cardMeta}>
        <span>
          {approval.project?.name}
          {approval.environment?.name && (
            <span className={`${styles.envTag} ${styles[`env_${approval.environment.name}`]}`}>
              {approval.environment.name}
            </span>
          )}
        </span>
        <span className={styles.dot}>·</span>
        <span>Requested by <strong>{approval.requested_by?.name}</strong></span>
        <span className={styles.dot}>·</span>
        <span>{formatRelativeTime(approval.created_at)}</span>
      </div>

      {approval.review_comment && (
        <p className={styles.reviewComment}>
          <strong>{approval.reviewed_by?.name}:</strong> {approval.review_comment}
        </p>
      )}

      <ApprovalActions
        approval={approval}
        showComment={false}
        onActionDone={onActionDone}
      />
    </div>
  )
}
