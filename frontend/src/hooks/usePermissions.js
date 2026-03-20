import { useAuth } from './useAuth'
import { hasPermission } from '../utils/permissions'

/**
 * Hook that exposes can(action, resource) based on the current user's role.
 *
 * @example
 *   const { can } = usePermissions()
 *   if (can('create', 'configs')) { ... }
 */
export function usePermissions() {
  const { user } = useAuth()
  const role = user?.role ?? null

  function can(action, resource) {
    if (!role) return false
    return hasPermission(role, resource, action)
  }

  return { can, role }
}
