import { useAuth } from '../../hooks/useAuth'
import { useNotification } from '../../context/NotificationContext'
import styles from './Header.module.css'

const ROLE_LABELS = { admin: 'Admin', editor: 'Editor', viewer: 'Viewer' }

export function Header() {
  const { user, logout } = useAuth()
  const { info } = useNotification()

  async function handleLogout() {
    await logout()
    info('Sesión cerrada correctamente.')
  }

  return (
    <header className={styles.header}>
      <div className={styles.brand}>
        <span className={styles.lockIcon}>🔒</span>
        <span className={styles.brandName}>Config Vault</span>
      </div>

      <div className={styles.userArea}>
        {user && (
          <>
            <span className={styles.userName}>{user.name}</span>
            <span className={`${styles.roleBadge} ${styles[`role_${user.role}`]}`}>
              {ROLE_LABELS[user.role] ?? user.role}
            </span>
          </>
        )}
        <button className={styles.logoutButton} onClick={handleLogout}>
          Logout
        </button>
      </div>
    </header>
  )
}
