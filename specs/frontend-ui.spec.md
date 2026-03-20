# Especificación: Frontend UI

**Versión:** 1.0  
**Estado:** Draft  
**Auth/Roles:** Ver `auth-and-roles.spec.md`  
**Modelos:** Ver `shared-contracts.spec.md`  
**API:** Ver `backend-api.spec.md`

---

## Fase 6 — Frontend completo

### 6.1 Routing

| Ruta | Componente | Auth | Rol mínimo |
|------|-----------|------|------------|
| `/login` | LoginForm | No | — |
| `/` | Dashboard (redirect a /projects) | Sí | Cualquiera |
| `/projects` | ProjectList | Sí | Cualquiera |
| `/projects/:id` | ProjectDetail | Sí | Cualquiera |
| `/projects/:id/env/:envId` | ConfigTable | Sí | Cualquiera |
| `/approvals` | ApprovalList | Sí | Admin, Editor |
| `/approvals/:id` | ApprovalDetail | Sí | Admin, Editor |
| `/users` | UserManagement | Sí | Admin |
| `/audit` | AuditLog | Sí | Admin |

### 6.2 Auth Context y flujo de login

**AuthContext provee:**
```javascript
{
  user: { id, name, email, role } | null,
  token: string | null,
  isAuthenticated: boolean,
  login: async (email, password) => void,
  logout: async () => void,
  isLoading: boolean
}
```

**Flujo:**
1. App carga → no hay token → redirect a `/login`
2. Usuario hace login → token se guarda en state (NUNCA localStorage)
3. Todas las requests usan el token via `api.js` wrapper
4. Si una request recibe 401 → limpiar auth state → redirect a `/login`
5. Logout → POST /api/auth/logout → limpiar state → redirect a `/login`

**ProtectedRoute:**
```jsx
// Envuelve rutas que requieren auth
<ProtectedRoute requiredRole="admin">
  <UserManagement />
</ProtectedRoute>
```
- Si no autenticado → redirect a `/login`
- Si autenticado pero rol insuficiente → mostrar página "403 - No autorizado"

### 6.3 Layout

```
┌──────────────────────────────────────────────────┐
│  🔒 Config Vault          Admin ▼ | [Logout]     │
├──────────┬───────────────────────────────────────┤
│          │                                        │
│ Projects │        Contenido principal             │
│ Approvals│                                        │
│ Users *  │                                        │
│ Audit *  │                                        │
│          │        (* = solo visible según rol)    │
│          │                                        │
└──────────┴───────────────────────────────────────┘
```

- Sidebar con links de navegación
- Items del sidebar se muestran/ocultan según rol del usuario
- Header muestra nombre del usuario, rol badge, y botón logout
- Indicador de rol en el header (badge con color)

### 6.4 LoginForm

```
┌─────────────────────────┐
│     🔒 Config Vault     │
│                         │
│  Email:    [__________] │
│  Password: [__________] │
│                         │
│       [  Login  ]       │
│                         │
│  ⚠️ Invalid credentials │  ← solo si error
└─────────────────────────┘
```

- Email + password inputs
- Botón Login → POST /api/auth/login
- Si error → mostrar mensaje bajo el formulario
- Si éxito → redirect a `/projects`
- Desactivar botón mientras carga

### 6.5 ProjectList

```
┌──────────────────────────────────────────────┐
│ Projects               [+ New Project] *     │
│                                              │
│ ┌──────────────────────────────────────────┐ │
│ │ Web Application                          │ │
│ │ Main web app configs                     │ │
│ │ 🟢 dev: 12 │ 🟡 stg: 10 │ 🔴 prod: 8  │ │
│ │ Owner: Editor User                       │ │
│ └──────────────────────────────────────────┘ │
│                                              │
│ * Botón solo visible para Admin y Editor     │
└──────────────────────────────────────────────┘
```

- Cada tarjeta muestra: nombre, descripción, conteo de configs por ambiente
- Click en tarjeta → `/projects/{id}`
- Botón "New Project" solo visible si `can("create", "projects")`

### 6.6 ProjectDetail + EnvironmentTabs

```
┌──────────────────────────────────────────────────┐
│ ← Projects                                       │
│                                                   │
│ Web Application                    [Edit] [Delete]│
│ Main web app configs                              │
│ Owner: Editor User                                │
│                                                   │
│ ┌─────────────┬──────────┬────────────┐          │
│ │ Development │ Staging  │ Production │          │
│ └─────────────┴──────────┴────────────┘          │
│                                                   │
│ [+ Add Config] *                   🔍 [Search..] │
│                                                   │
│ ┌─ Key ──────────── Type ── Value ── Actions ──┐ │
│ │ DATABASE_URL      Aa str  postgres://...  ✏️🗑│ │
│ │ ENABLE_CACHE      🚩 flag  ● ON          ⟳  │ │
│ │ API_SECRET        🔒 sec  ********      👁✏️🗑│ │
│ │ MAX_CONNECTIONS   #  num   100           ✏️🗑│ │
│ └──────────────────────────────────────────────┘ │
│                                                   │
│ * Solo visible para Admin y Editor                │
│ ⟳ = toggle para feature flags                    │
│ 👁 = reveal secret (genera audit log)             │
└───────────────────────────────────────────────────┘
```

**Tabs de ambiente:**
- Click en tab → carga configs de ese ambiente
- Tab activo resaltado
- Production tab con icono de candado 🔒

**Tabla de configs:**
- Columnas: Key, Type (con icono), Value, Actions
- Secrets muestran `********` con botón reveal (👁)
- Feature flags muestran toggle visual (ON/OFF)
- Acciones por config según permisos:
  - Edit (✏️): Admin y Editor (en production, Editor genera approval)
  - Delete (🗑): Admin en cualquier env, Editor solo dev/staging
  - Reveal (👁): Admin y Editor para secrets
  - Toggle (⟳): Admin y Editor para feature flags

**ConfigEditor (modal):**
```
┌────────────────────────────────────┐
│ Create Config                      │
│                                    │
│ Key:         [________________]    │
│ Type:        [string      ▼]      │
│ Value:       [________________]    │
│ Description: [________________]    │
│                                    │
│ ⚠️ This environment requires       │
│    approval for changes.           │
│                                    │
│         [Cancel] [Save]            │
└────────────────────────────────────┘
```

- Input "Value" cambia según tipo:
  - `string`: textarea
  - `number`: input type=number
  - `boolean`: toggle switch
  - `json`: textarea con validación JSON
  - `secret`: password input con show/hide
  - `feature_flag`: toggle switch
- Si el ambiente requiere aprobación, mostrar advertencia
- Al guardar en ambiente con approval → toast "Approval request created"

### 6.7 ApprovalList

```
┌──────────────────────────────────────────────────┐
│ Approvals              Status: [Pending ▼]       │
│                                                   │
│ ┌──────────────────────────────────────────────┐ │
│ │ 🟡 PENDING  Create NEW_API_KEY               │ │
│ │ Project: Web App → production                 │ │
│ │ Requested by: Editor User • 10 min ago        │ │
│ │                                               │ │
│ │ [Approve] [Reject]    ← solo Admin            │ │
│ │ [Cancel]              ← solo el solicitante   │ │
│ └──────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────┘
```

- Admin ve TODAS las solicitudes pendientes
- Editor ve solo sus propias solicitudes
- Filtro por status
- Acciones según rol (ver auth-and-roles spec)

### 6.8 ApprovalDetail

```
┌───────────────────────────────────────────────────┐
│ ← Approvals                                       │
│                                                    │
│ Approval #5                          🟡 PENDING   │
│                                                    │
│ Action:      Create config                         │
│ Project:     Web Application                       │
│ Environment: production                            │
│ Key:         NEW_API_KEY                           │
│ Type:        secret                                │
│                                                    │
│ ┌─ Proposed Change ──────────────────────────────┐│
│ │ Current value: (none — new config)             ││
│ │ Proposed value: ********                       ││
│ └────────────────────────────────────────────────┘│
│                                                    │
│ Requested by: Editor User                          │
│ Date: March 17, 2026 at 12:00 PM                  │
│                                                    │
│ ┌─ Admin Actions ────────────────────────────────┐│
│ │ Comment: [___________________________________] ││
│ │                                                ││
│ │ [✅ Approve]  [❌ Reject]                      ││
│ └────────────────────────────────────────────────┘│
│                                                    │
│ ← Solo visible para Admin                          │
└────────────────────────────────────────────────────┘
```

- Muestra diff entre valor actual y propuesto
- Admin puede aprobar/rechazar con comentario
- Editor (solicitante) puede cancelar si aún está pending

### 6.9 UserManagement (Admin only)

```
┌──────────────────────────────────────────────────┐
│ Users                          [+ Create User]   │
│                                                   │
│ ┌─ Name ──────── Email ────── Role ── Status ──┐ │
│ │ Admin User    admin@...     🛡️ admin   ● Active│ │
│ │ Editor User   editor@...    ✏️ editor  ● Active│ │
│ │ Viewer User   viewer@...    👁 viewer  ○ Inactive│ │
│ └──────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────┘
```

- Tabla con todos los usuarios
- Crear usuario (modal con name, email, password, role)
- Editar rol (dropdown en la tabla)
- Toggle active/inactive
- No puede desactivarse a sí mismo

### 6.10 AuditLog (Admin only — log global)

```
┌──────────────────────────────────────────────────┐
│ Audit Log                        [Export CSV]    │
│                                                   │
│ Action: [All ▼] User: [All ▼] Project: [All ▼]  │
│ From: [________] To: [________]                   │
│                                                   │
│ ┌──────────────────────────────────────────────┐ │
│ │ 11:30 AM  Admin User  config_updated          │ │
│ │           Web App → staging → DATABASE_URL    │ │
│ │           Value changed (v2 → v3)             │ │
│ ├──────────────────────────────────────────────┤ │
│ │ 11:15 AM  Editor User  approval_requested     │ │
│ │           Web App → production → NEW_API_KEY  │ │
│ │           Action: create                      │ │
│ ├──────────────────────────────────────────────┤ │
│ │ 11:00 AM  Admin User  login                   │ │
│ │           IP: 127.0.0.1                       │ │
│ └──────────────────────────────────────────────┘ │
│                                                   │
│        [← Previous]  Page 1 of 12  [Next →]     │
└──────────────────────────────────────────────────┘
```

- Filtros: action, user, project, rango de fechas
- Cada entrada muestra timestamp, usuario, acción, contexto
- Paginación
- Botón Export CSV (solo Admin)

### 6.11 Notifications (Toast)

Usar un `NotificationContext` simple que muestra toasts temporales (3 segundos):

| Tipo | Color | Cuándo |
|------|-------|--------|
| success | verde | Operación exitosa (crear, editar, aprobar) |
| error | rojo | Error del API o validación |
| warning | amarillo | Approval required (cuando editor en production) |
| info | azul | Informativo (logout exitoso) |

```
┌──────────────────────────────────┐
│ ✅ Config created successfully    │  ← toast temporal
└──────────────────────────────────┘
```

---

**Criterios de aceptación Fase 6:**
- [ ] Login/logout funciona, token en memory (no localStorage)
- [ ] Redirect a login si token expirado
- [ ] Sidebar muestra items según rol
- [ ] ProtectedRoute bloquea acceso por rol insuficiente
- [ ] ProjectList muestra proyectos con conteo de configs
- [ ] EnvironmentTabs permiten navegar entre dev/staging/production
- [ ] ConfigTable muestra configs con iconos por tipo
- [ ] Secrets muestran ******** con reveal funcional
- [ ] Feature flags tienen toggle visual
- [ ] ConfigEditor valida tipos y muestra warning de approval
- [ ] ApprovalList filtra por rol (admin=todas, editor=propias)
- [ ] Admin puede aprobar/rechazar con comentario
- [ ] UserManagement funciona (solo admin)
- [ ] AuditLog muestra entradas con filtros
- [ ] Export CSV funciona
- [ ] Toasts aparecen para cada acción
- [ ] Viewer no ve botones de acción (crear, editar, eliminar)

---

## Fase 7 — Tests E2E y cierre

### Escenarios multi-rol para verificar

**Escenario 1: Flujo completo de un Editor**
1. Login como Editor
2. Crear un proyecto "My App"
3. Agregar configs en development: DB_URL (string), DEBUG (boolean), API_KEY (secret)
4. Agregar config en production: PROD_DB_URL → debe generar approval request
5. Ver la approval en /approvals → status pending
6. Login como Admin → aprobar → verificar config creada en production
7. Verificar audit log tiene todas las acciones

**Escenario 2: Viewer no puede hacer nada**
1. Login como Viewer
2. Ver proyectos → OK
3. Ver configs → OK, secrets muestran ********
4. Intentar crear config → no hay botón, API rechaza si se intenta
5. No ve /users ni /audit global
6. /approvals no accesible

**Escenario 3: Admin gestiona todo**
1. Login como Admin
2. Crear usuario Editor
3. Crear proyecto, configs en todos los ambientes (directo, sin approval)
4. Ver audit log completo
5. Exportar CSV
6. Desactivar un usuario → ese usuario no puede loguearse

**Escenario 4: Aprobación rechazada**
1. Editor crea config en production → approval pending
2. Admin rechaza con comentario
3. Config NO se crea en production
4. Editor ve el rechazo con comentario

**Criterios de aceptación Fase 7:**
- [ ] Los 4 escenarios multi-rol funcionan end-to-end
- [ ] Backend tests pasan (pytest)
- [ ] La matriz de permisos se verifica exhaustivamente en tests
- [ ] Cada acción genera audit log correcto
- [ ] Secrets nunca aparecen en logs ni en audit
- [ ] Redis cache funciona (y sistema funciona sin Redis)
- [ ] README.md documenta setup, arquitectura, roles, y API
