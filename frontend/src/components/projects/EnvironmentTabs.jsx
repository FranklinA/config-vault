import styles from './EnvironmentTabs.module.css'

const ENV_ORDER = ['development', 'staging', 'production']

const ENV_META = {
  development: { label: 'Development', icon: null },
  staging:     { label: 'Staging',     icon: null },
  production:  { label: 'Production',  icon: '🔒' },
}

export function EnvironmentTabs({ environments, activeEnvId, onSelect }) {
  const ordered = ENV_ORDER
    .map(name => environments?.find(e => e.name === name))
    .filter(Boolean)

  return (
    <div className={styles.tabs}>
      {ordered.map(env => {
        const meta = ENV_META[env.name] ?? { label: env.name, icon: null }
        const isActive = env.id === activeEnvId
        return (
          <button
            key={env.id}
            className={`${styles.tab} ${isActive ? styles.active : ''} ${styles[env.name]}`}
            onClick={() => onSelect(env)}
          >
            {meta.icon && <span className={styles.tabIcon}>{meta.icon}</span>}
            {meta.label}
            {env.require_approval && !isActive && (
              <span className={styles.approvalDot} title="Requires approval" />
            )}
          </button>
        )
      })}
    </div>
  )
}
