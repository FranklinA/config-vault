import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../../hooks/useAuth'
import styles from './ProtectedRoute.module.css'

const ROLE_RANK = { viewer: 0, editor: 1, admin: 2 }

export function ProtectedRoute({ children, requiredRole }) {
  const { isAuthenticated, user } = useAuth()
  const location = useLocation()

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  if (requiredRole && ROLE_RANK[user.role] < ROLE_RANK[requiredRole]) {
    return (
      <div className={styles.forbidden}>
        <h1>403</h1>
        <p>No tienes permiso para acceder a esta página.</p>
      </div>
    )
  }

  return children
}
