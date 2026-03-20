import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { api } from '../../utils/api'
import { useNotification } from '../../context/NotificationContext'
import { ApprovalActions } from './ApprovalActions'
import { STATUS_META, ACTION_LABELS } from './ApprovalList'
import styles from './ApprovalDetail.module.css'

const TYPE_ICONS = {
  string:       'Aa',
  number:       '#',
  boolean:      '⊘',
  json:         '{}',
  secret:       '🔒',
  feature_flag: '🚩',
}

function formatDateTime(dateStr) {
  if (!dateStr) return '—'
  return new Date(dateStr).toLocaleString('en-US', {
    year: 'numeric', month: 'long', day: 'numeric',
    hour: 'numeric', minute: '2-digit',
  })
}

function ValueDisplay({ value, configType, label }) {
  const isSecret = configType === 'secret'
  const isEmpty  = value == null || value === ''

  return (
    <div className={styles.diffRow}>
      <span className={styles.diffLabel}>{label}</span>
      <code className={`${styles.diffValue} ${isEmpty ? styles.diffEmpty : ''}`}>
        {isEmpty
          ? '(none)'
          : isSecret
          ? '••••••••'
          : value}
      </code>
    </div>
  )
}

export function ApprovalDetail() {
  const { approvalId } = useParams()
  const { error } = useNotification()

  const [approval, setApproval] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function load() {
      setLoading(true)
      try {
        const data = await api.get(`/api/approvals/${approvalId}`)
        setApproval(data)
      } catch (err) {
        error(err.message)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [approvalId])

  function handleActionDone(updated) {
    setApproval(updated)
  }

  if (loading) return <div className={styles.loading}>Cargando solicitud…</div>
  if (!approval) return <div className={styles.loading}>Solicitud no encontrada.</div>

  const meta = STATUS_META[approval.status] ?? STATUS_META.pending

  return (
    <div className={styles.page}>
      <Link to="/approvals" className={styles.backLink}>← Approvals</Link>

      {/* ── Header ── */}
      <div className={styles.header}>
        <h1 className={styles.title}>Approval #{approval.id}</h1>
        <span className={`${styles.statusBadge} ${styles[meta.cls]}`}>
          {meta.icon} {meta.label}
        </span>
      </div>

      {/* ── Details ── */}
      <div className={styles.detailsCard}>
        <DetailRow label="Action"      value={ACTION_LABELS[approval.action] ?? approval.action} />
        <DetailRow label="Project"     value={approval.project?.name} />
        <DetailRow label="Environment" value={
          <span className={`${styles.envTag} ${styles[`env_${approval.environment?.name}`]}`}>
            {approval.environment?.name}
          </span>
        } />
        <DetailRow label="Key"         value={<code className={styles.key}>{approval.key}</code>} />
        <DetailRow label="Type"        value={
          <span className={styles.typeLabel}>
            <span>{TYPE_ICONS[approval.config_type] ?? '?'}</span> {approval.config_type}
          </span>
        } />
      </div>

      {/* ── Proposed change diff ── */}
      <div className={styles.section}>
        <h2 className={styles.sectionTitle}>Proposed Change</h2>
        <div className={styles.diffBox}>
          <ValueDisplay
            label="Current value"
            value={approval.current_value}
            configType={approval.config_type}
          />
          <div className={styles.diffDivider} />
          <ValueDisplay
            label="Proposed value"
            value={approval.proposed_value}
            configType={approval.config_type}
          />
        </div>
      </div>

      {/* ── Requester info ── */}
      <div className={styles.section}>
        <div className={styles.requestInfo}>
          <span>
            Requested by <strong>{approval.requested_by?.name}</strong>
          </span>
          <span className={styles.dot}>·</span>
          <span>{formatDateTime(approval.created_at)}</span>
        </div>
      </div>

      {/* ── Review info (if already reviewed) ── */}
      {approval.reviewed_by && (
        <div className={styles.section}>
          <h2 className={styles.sectionTitle}>Review</h2>
          <div className={styles.reviewBox}>
            <div className={styles.reviewMeta}>
              <span><strong>{approval.reviewed_by.name}</strong></span>
              <span className={styles.dot}>·</span>
              <span>{formatDateTime(approval.reviewed_at)}</span>
            </div>
            {approval.review_comment && (
              <p className={styles.reviewComment}>{approval.review_comment}</p>
            )}
          </div>
        </div>
      )}

      {/* ── Actions (admin approve/reject with comment, or editor cancel) ── */}
      {approval.status === 'pending' && (
        <div className={styles.section}>
          <h2 className={styles.sectionTitle}>Actions</h2>
          <div className={styles.actionsBox}>
            <ApprovalActions
              approval={approval}
              showComment={true}
              onActionDone={handleActionDone}
            />
          </div>
        </div>
      )}
    </div>
  )
}

function DetailRow({ label, value }) {
  return (
    <div className={styles.detailRow}>
      <span className={styles.detailLabel}>{label}</span>
      <span className={styles.detailValue}>{value}</span>
    </div>
  )
}
