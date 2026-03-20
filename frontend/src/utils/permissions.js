/**
 * Frontend permission matrix — mirrors backend app/permissions.py exactly.
 * The backend is always the authoritative source; this is for UI show/hide only.
 */

export const PERMISSIONS = {
  admin: {
    users: ['list', 'create', 'edit_role', 'deactivate'],
    projects: ['list', 'create', 'edit', 'delete', 'view'],
    configs: ['list', 'view', 'view_secret', 'create', 'edit', 'delete'],
    configs_production: ['create_direct', 'edit_direct', 'delete'],
    approvals: ['list_all', 'approve', 'reject'],
    audit: ['view_all', 'export'],
  },
  editor: {
    users: [],
    projects: ['list', 'create', 'edit_own', 'view'],
    configs: ['list', 'view', 'view_secret', 'create', 'edit', 'delete'],
    configs_production: ['create_with_approval', 'edit_with_approval'],
    approvals: ['list_own', 'create', 'cancel_own'],
    audit: ['view_project'],
  },
  viewer: {
    users: [],
    projects: ['list', 'view'],
    configs: ['list', 'view'],
    configs_production: [],
    approvals: [],
    audit: ['view_project'],
  },
}

/**
 * Check if a role has a given permission.
 * @param {string} role - 'admin' | 'editor' | 'viewer'
 * @param {string} resource - e.g. 'configs', 'projects'
 * @param {string} action - e.g. 'create', 'view_secret'
 * @returns {boolean}
 */
export function hasPermission(role, resource, action) {
  const rolePerms = PERMISSIONS[role]
  if (!rolePerms) return false
  const resourcePerms = rolePerms[resource]
  if (!resourcePerms) return false
  return resourcePerms.includes(action)
}
