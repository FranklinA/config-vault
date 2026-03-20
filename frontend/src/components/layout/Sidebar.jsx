import { NavLink } from 'react-router-dom'
import { usePermissions } from '../../hooks/usePermissions'
import styles from './Sidebar.module.css'

const NAV_ITEMS = [
  {
    to: '/projects',
    label: 'Projects',
    icon: '📁',
    // visible to all authenticated users
  },
  {
    to: '/approvals',
    label: 'Approvals',
    icon: '✅',
    roles: ['admin', 'editor'],
  },
  {
    to: '/users',
    label: 'Users',
    icon: '👥',
    roles: ['admin'],
  },
  {
    to: '/audit',
    label: 'Audit Log',
    icon: '📋',
    roles: ['admin'],
  },
]

export function Sidebar() {
  const { role } = usePermissions()

  const visibleItems = NAV_ITEMS.filter(item =>
    !item.roles || item.roles.includes(role)
  )

  return (
    <nav className={styles.sidebar}>
      <ul className={styles.navList}>
        {visibleItems.map(item => (
          <li key={item.to}>
            <NavLink
              to={item.to}
              className={({ isActive }) =>
                `${styles.navLink} ${isActive ? styles.active : ''}`
              }
            >
              <span className={styles.navIcon}>{item.icon}</span>
              {item.label}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  )
}
