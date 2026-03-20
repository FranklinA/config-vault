import { useState } from 'react'
import { api } from '../../utils/api'
import { usePermissions } from '../../hooks/usePermissions'
import { useNotification } from '../../context/NotificationContext'
import { Modal } from '../common/Modal'
import styles from './ConfigEditor.module.css'

const CONFIG_TYPES = ['string', 'number', 'boolean', 'json', 'secret', 'feature_flag']

/**
 * Modal for creating or editing a config entry.
 *
 * @param {object|null} config      - Existing config for edit, null for create
 * @param {number}      projectId
 * @param {object}      env         - { id, name, require_approval }
 * @param {function}    onClose
 * @param {function}    onSaved     - (result) => void  (result may be config or approval obj)
 */
export function ConfigEditor({ config, projectId, env, onClose, onSaved }) {
  const isEdit = !!config
  const { role } = usePermissions()
  const { success, warn, error } = useNotification()

  const [key, setKey] = useState(config?.key ?? '')
  const [configType, setConfigType] = useState(config?.config_type ?? 'string')
  const [value, setValue] = useState(
    // For secrets in edit mode, start blank so user consciously re-enters
    (isEdit && config.config_type === 'secret') ? '' : (config?.value ?? '')
  )
  const [description, setDescription] = useState(config?.description ?? '')
  const [showPassword, setShowPassword] = useState(false)
  const [saving, setSaving] = useState(false)
  const [errors, setErrors] = useState({})

  const requiresApproval = env.require_approval && role === 'editor'

  function validate() {
    const errs = {}
    if (!isEdit && !key.trim()) errs.key = 'La key es requerida.'
    if (!isEdit && !/^[A-Z0-9_]+$/i.test(key.trim())) errs.key = 'Solo letras, números y guiones bajos.'
    if (!value.trim() && configType !== 'boolean' && configType !== 'feature_flag') {
      errs.value = 'El valor es requerido.'
    }
    if (configType === 'number' && isNaN(Number(value))) {
      errs.value = 'Debe ser un número válido.'
    }
    if (configType === 'json') {
      try { JSON.parse(value) } catch { errs.value = 'JSON inválido.' }
    }
    if ((configType === 'boolean' || configType === 'feature_flag') && !['true', 'false'].includes(value)) {
      errs.value = 'Debe ser "true" o "false".'
    }
    return errs
  }

  async function handleSubmit(e) {
    e.preventDefault()
    const errs = validate()
    if (Object.keys(errs).length) { setErrors(errs); return }

    setSaving(true)
    setErrors({})
    try {
      const url = isEdit
        ? `/api/projects/${projectId}/environments/${env.id}/configs/${config.id}`
        : `/api/projects/${projectId}/environments/${env.id}/configs`

      const body = isEdit
        ? { value, description }
        : { key: key.trim(), value, config_type: configType, description }

      const result = isEdit
        ? await api.put(url, body)
        : await api.post(url, body)

      if (result?.approval_request) {
        warn('Approval request created for production change.')
        onSaved({ approvalCreated: true, approval: result.approval_request })
      } else {
        success(isEdit ? 'Config actualizada.' : 'Config creada.')
        onSaved(result)
      }
      onClose()
    } catch (err) {
      error(err.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal title={isEdit ? 'Edit Config' : 'Create Config'} onClose={onClose}>
      <form onSubmit={handleSubmit} className={styles.form}>
        {/* Key — only editable on create */}
        <div className={styles.field}>
          <label className={styles.label}>Key *</label>
          <input
            className={`${styles.input} ${errors.key ? styles.inputError : ''}`}
            value={key}
            onChange={e => { setKey(e.target.value.toUpperCase()); setErrors(p => ({ ...p, key: null })) }}
            placeholder="DATABASE_URL"
            disabled={isEdit || saving}
          />
          {errors.key && <span className={styles.err}>{errors.key}</span>}
        </div>

        {/* Type — only selectable on create */}
        <div className={styles.field}>
          <label className={styles.label}>Type</label>
          <select
            className={styles.select}
            value={configType}
            onChange={e => { setConfigType(e.target.value); setValue('') }}
            disabled={isEdit || saving}
          >
            {CONFIG_TYPES.map(t => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        </div>

        {/* Value — input adapts per type */}
        <div className={styles.field}>
          <label className={styles.label}>
            Value *{isEdit && configType === 'secret' && (
              <span className={styles.hint}> (re-enter to update)</span>
            )}
          </label>
          <ValueInput
            configType={configType}
            value={value}
            onChange={v => { setValue(v); setErrors(p => ({ ...p, value: null })) }}
            showPassword={showPassword}
            onTogglePassword={() => setShowPassword(p => !p)}
            disabled={saving}
          />
          {errors.value && <span className={styles.err}>{errors.value}</span>}
        </div>

        {/* Description */}
        <div className={styles.field}>
          <label className={styles.label}>Description</label>
          <input
            className={styles.input}
            value={description}
            onChange={e => setDescription(e.target.value)}
            placeholder="Optional description…"
            disabled={saving}
          />
        </div>

        {/* Approval warning */}
        {requiresApproval && (
          <div className={styles.approvalWarning}>
            <span>⚠️</span>
            <span>
              El ambiente <strong>production</strong> requiere aprobación. Se creará una
              solicitud de aprobación en lugar de aplicar el cambio directamente.
            </span>
          </div>
        )}

        <div className={styles.actions}>
          <button type="button" className={styles.btnSecondary} onClick={onClose} disabled={saving}>
            Cancel
          </button>
          <button type="submit" className={styles.btnPrimary} disabled={saving}>
            {saving
              ? 'Saving…'
              : requiresApproval
              ? 'Submit for Approval'
              : isEdit ? 'Save Changes' : 'Create'}
          </button>
        </div>
      </form>
    </Modal>
  )
}

function ValueInput({ configType, value, onChange, showPassword, onTogglePassword, disabled }) {
  switch (configType) {
    case 'boolean':
    case 'feature_flag':
      return (
        <div className={styles.boolToggle}>
          {['true', 'false'].map(opt => (
            <label key={opt} className={styles.radioLabel}>
              <input
                type="radio"
                name="bool_value"
                value={opt}
                checked={value === opt}
                onChange={() => onChange(opt)}
                disabled={disabled}
              />
              {opt}
            </label>
          ))}
        </div>
      )

    case 'number':
      return (
        <input
          type="number"
          className={styles.input}
          value={value}
          onChange={e => onChange(e.target.value)}
          placeholder="0"
          disabled={disabled}
          step="any"
        />
      )

    case 'json':
      return (
        <textarea
          className={`${styles.textarea} ${styles.mono}`}
          value={value}
          onChange={e => onChange(e.target.value)}
          placeholder='{"key": "value"}'
          rows={5}
          disabled={disabled}
          spellCheck={false}
        />
      )

    case 'secret':
      return (
        <div className={styles.passwordWrapper}>
          <input
            type={showPassword ? 'text' : 'password'}
            className={styles.input}
            value={value}
            onChange={e => onChange(e.target.value)}
            placeholder="Secret value"
            disabled={disabled}
            autoComplete="new-password"
          />
          <button
            type="button"
            className={styles.eyeBtn}
            onClick={onTogglePassword}
            tabIndex={-1}
          >
            {showPassword ? '🙈' : '👁'}
          </button>
        </div>
      )

    default: // string
      return (
        <textarea
          className={styles.textarea}
          value={value}
          onChange={e => onChange(e.target.value)}
          placeholder="Value…"
          rows={3}
          disabled={disabled}
        />
      )
  }
}
