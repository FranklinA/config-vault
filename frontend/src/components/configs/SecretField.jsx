import { useState } from 'react'
import { api } from '../../utils/api'
import { useNotification } from '../../context/NotificationContext'
import styles from './SecretField.module.css'

/**
 * Table-cell display for secrets.
 * Shows "********" by default; reveal button calls the /reveal endpoint.
 *
 * @param {number}  projectId
 * @param {number}  envId
 * @param {number}  configId
 * @param {boolean} canReveal   - true for admin and editor
 */
export function SecretField({ projectId, envId, configId, canReveal }) {
  const [revealed, setRevealed] = useState(null)  // null = masked
  const [loading, setLoading] = useState(false)
  const { error } = useNotification()

  async function handleReveal() {
    if (loading) return
    if (revealed !== null) {
      setRevealed(null)  // hide again
      return
    }
    setLoading(true)
    try {
      const data = await api.post(
        `/api/projects/${projectId}/environments/${envId}/configs/${configId}/reveal`
      )
      setRevealed(data.value)
    } catch (err) {
      error(err.message)
    } finally {
      setLoading(false)
    }
  }

  const isRevealed = revealed !== null

  return (
    <span className={styles.wrapper}>
      <code className={`${styles.value} ${isRevealed ? styles.plain : styles.masked}`}>
        {isRevealed ? revealed : '••••••••'}
      </code>
      {canReveal && (
        <button
          className={styles.revealBtn}
          onClick={handleReveal}
          disabled={loading}
          title={isRevealed ? 'Ocultar' : 'Revelar valor'}
          type="button"
        >
          {isRevealed ? '🙈' : '👁'}
        </button>
      )}
    </span>
  )
}
