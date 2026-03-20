import { useState } from 'react'
import { api } from '../../utils/api'
import { useNotification } from '../../context/NotificationContext'
import styles from './FeatureFlagToggle.module.css'

/**
 * Renders an ON/OFF toggle for a feature_flag config.
 * Calls PUT .../toggle on change and reports the updated config.
 *
 * @param {string}   value       - "true" | "false"
 * @param {number}   projectId
 * @param {number}   envId
 * @param {number}   configId
 * @param {boolean}  disabled    - when user cannot edit
 * @param {function} onChange    - (updatedConfig) => void
 */
export function FeatureFlagToggle({ value, projectId, envId, configId, disabled, onChange }) {
  const isOn = value === 'true'
  const [busy, setBusy] = useState(false)
  const { success, warn, error } = useNotification()

  async function handleToggle() {
    if (disabled || busy) return
    setBusy(true)
    try {
      const updated = await api.put(
        `/api/projects/${projectId}/environments/${envId}/configs/${configId}/toggle`
      )
      // 202 = approval created (no config returned directly)
      if (updated?.approval_request) {
        warn('Toggle submitted — approval required for production.')
        onChange?.(null)
      } else {
        success(`Flag turned ${updated.value === 'true' ? 'ON' : 'OFF'}.`)
        onChange?.(updated)
      }
    } catch (err) {
      error(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <button
      className={`${styles.toggle} ${isOn ? styles.on : styles.off}`}
      onClick={handleToggle}
      disabled={disabled || busy}
      title={disabled ? 'Sin permiso' : `Toggle to ${isOn ? 'OFF' : 'ON'}`}
      type="button"
    >
      <span className={styles.thumb} />
      <span className={styles.label}>{isOn ? 'ON' : 'OFF'}</span>
    </button>
  )
}
