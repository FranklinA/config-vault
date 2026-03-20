import styles from './AuditEntry.module.css'

const ACTION_ICONS = {
  login:                '🔑',
  logout:               '🚪',
  login_failed:         '🚫',
  user_created:         '👤',
  user_updated:         '✏️',
  project_created:      '📁',
  project_updated:      '📝',
  project_deleted:      '🗑',
  config_created:       '➕',
  config_updated:       '🔄',
  config_deleted:       '🗑',
  approval_requested:   '📋',
  approval_approved:    '✅',
  approval_rejected:    '❌',
  approval_cancelled:   '⊘',
  secret_accessed:      '👁',
}

function formatTime(dateStr) {
  return new Date(dateStr).toLocaleString('en-US', {
    month: 'short', day: 'numeric',
    hour: 'numeric', minute: '2-digit',
  })
}

/**
 * Derives a human-readable context line from the details object.
 */
function buildContext(entry) {
  const d = entry.details ?? {}
  const parts = []

  if (entry.project?.name) parts.push(entry.project.name)
  if (d.environment)        parts.push(d.environment)
  if (d.key)                parts.push(d.key)

  const context = parts.join(' → ')

  const notes = []
  if (d.version)                    notes.push(`v${d.version}`)
  if (d.action)                     notes.push(`action: ${d.action}`)
  if (d.note)                       notes.push(d.note)
  if (entry.ip_address && !d.key)   notes.push(`IP: ${entry.ip_address}`)

  return { context, note: notes.join(' · ') }
}

export function AuditEntry({ entry }) {
  const icon = ACTION_ICONS[entry.action] ?? '•'
  const { context, note } = buildContext(entry)

  return (
    <div className={styles.entry}>
      <div className={styles.left}>
        <span className={styles.icon}>{icon}</span>
      </div>
      <div className={styles.body}>
        <div className={styles.headline}>
          <span className={styles.time}>{formatTime(entry.created_at)}</span>
          <span className={styles.user}>{entry.user?.name ?? '—'}</span>
          <code className={styles.action}>{entry.action}</code>
        </div>
        {context && <div className={styles.context}>{context}</div>}
        {note    && <div className={styles.note}>{note}</div>}
      </div>
    </div>
  )
}
