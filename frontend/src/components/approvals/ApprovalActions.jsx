import { useState } from 'react'
import { api } from '../../utils/api'
import { useAuth } from '../../hooks/useAuth'
import { useNotification } from '../../context/NotificationContext'
import styles from './ApprovalActions.module.css'

/**
 * Renders action buttons for an approval based on the current user's role.
 *
 * @param {object}   approval        - ApprovalRequestResponse
 * @param {boolean}  showComment     - If true, renders a comment textarea before buttons
 * @param {function} onActionDone    - (updatedApproval) => void
 */
export function ApprovalActions({ approval, showComment = false, onActionDone }) {
  const { user } = useAuth()
  const { success, error } = useNotification()

  const [comment, setComment] = useState('')
  const [busy, setBusy] = useState(null)  // 'approve' | 'reject' | 'cancel'

  const isAdmin   = user?.role === 'admin'
  const isOwner   = user?.id === approval.requested_by?.id
  const isPending = approval.status === 'pending'

  const canApproveReject = isAdmin && isPending
  const canCancel        = isOwner && isPending && !isAdmin  // admin never needs to cancel

  if (!canApproveReject && !canCancel) return null

  async function act(action) {
    setBusy(action)
    try {
      const body = action !== 'cancel' ? { comment } : undefined
      const updated = await api.post(`/api/approvals/${approval.id}/${action}`, body)
      const labels = { approve: 'aprobada', reject: 'rechazada', cancel: 'cancelada' }
      success(`Solicitud ${labels[action]}.`)
      onActionDone?.(updated)
    } catch (err) {
      error(err.message)
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className={styles.wrapper}>
      {showComment && canApproveReject && (
        <div className={styles.commentField}>
          <label className={styles.commentLabel}>Comment (optional)</label>
          <textarea
            className={styles.commentInput}
            value={comment}
            onChange={e => setComment(e.target.value)}
            placeholder="Add a comment for the requester…"
            rows={3}
            disabled={!!busy}
          />
        </div>
      )}

      <div className={styles.buttons}>
        {canApproveReject && (
          <>
            <button
              className={styles.btnApprove}
              onClick={() => act('approve')}
              disabled={!!busy}
            >
              {busy === 'approve' ? 'Approving…' : '✅ Approve'}
            </button>
            <button
              className={styles.btnReject}
              onClick={() => act('reject')}
              disabled={!!busy}
            >
              {busy === 'reject' ? 'Rejecting…' : '❌ Reject'}
            </button>
          </>
        )}

        {canCancel && (
          <button
            className={styles.btnCancel}
            onClick={() => act('cancel')}
            disabled={!!busy}
          >
            {busy === 'cancel' ? 'Cancelling…' : 'Cancel Request'}
          </button>
        )}
      </div>
    </div>
  )
}
