# Especificación: Autenticación y Roles

**Versión:** 1.0  
**Estado:** Draft  

**⚠️ ESTE ARCHIVO define QUIÉN puede hacer QUÉ en el sistema.
Todos los endpoints y componentes de UI DEBEN respetar esta spec.
Cuando tengas dudas sobre si una operación está permitida, consulta
la matriz de permisos en la sección 4.**

---

## 1. Autenticación (JWT)

### 1.1 Flujo de login

```
Cliente                          Backend
  │                                │
  │  POST /api/auth/login          │
  │  { email, password }           │
  │ ─────────────────────────────► │
  │                                │ Validar credenciales
  │                                │ Generar JWT access token
  │  200 OK                        │
  │  { access_token, token_type,   │
  │    user: { id, name, email,    │
  │            role } }            │
  │ ◄───────────────────────────── │
  │                                │
  │  GET /api/configs (ejemplo)    │
  │  Header: Authorization:        │
  │    Bearer <access_token>       │
  │ ─────────────────────────────► │
  │                                │ Verificar JWT
  │                                │ Extraer user_id + role
  │                                │ Verificar permisos
  │  200 OK / 403 Forbidden        │
  │ ◄───────────────────────────── │
```

### 1.2 Estructura del JWT

**Payload:**
```json
{
  "sub": "user_id_as_string",
  "email": "user@example.com",
  "role": "admin",
  "exp": 1711234567,
  "iat": 1711232767
}
```

- `sub`: user ID como string
- `exp`: expiración (30 minutos desde emisión)
- `iat`: issued at
- Algoritmo: HS256
- Secret: configurado en `app/config.py`

### 1.3 Manejo de tokens

- **Access token**: 30 minutos de vida. Se envía en header `Authorization: Bearer <token>`.
- **Refresh token**: NO se implementa en este proyecto. Cuando el token expira, el usuario debe re-loguearse.
- **Revocación**: Al hacer logout, el token se agrega a una blacklist en Redis (TTL = tiempo restante del token).
- **Verificación en cada request**: middleware verifica firma + expiración + blacklist.

### 1.4 Respuestas de auth

| Situación | Status | Respuesta |
|-----------|--------|-----------|
| Login exitoso | 200 | `{ access_token, token_type, user }` |
| Credenciales inválidas | 401 | `{ detail: { code: "INVALID_CREDENTIALS", message: "..." } }` |
| Token faltante | 401 | `{ detail: { code: "TOKEN_REQUIRED", message: "..." } }` |
| Token expirado | 401 | `{ detail: { code: "TOKEN_EXPIRED", message: "..." } }` |
| Token inválido | 401 | `{ detail: { code: "INVALID_TOKEN", message: "..." } }` |
| Token revocado | 401 | `{ detail: { code: "TOKEN_REVOKED", message: "..." } }` |
| Sin permiso | 403 | `{ detail: { code: "FORBIDDEN", message: "..." } }` |

---

## 2. Roles

El sistema tiene 3 roles fijos (no configurables):

### Admin
- Acceso total al sistema
- Gestionar usuarios (crear, editar rol, desactivar)
- Aprobar/rechazar cambios a producción
- Ver audit log completo
- Gestionar todos los proyectos y configuraciones

### Editor
- Crear y gestionar proyectos
- Crear/editar/eliminar configuraciones en dev y staging
- Crear configuraciones en production (requiere aprobación)
- Editar configuraciones en production (requiere aprobación)
- Crear solicitudes de aprobación
- Ver audit log de sus propios proyectos

### Viewer
- Ver proyectos y configuraciones (solo lectura)
- Ver valores de configs (excepto secrets — ve `********`)
- No puede crear, editar, ni eliminar nada
- Ver audit log de los proyectos que puede ver

---

## 3. Modelo: User

| Campo | Tipo | Nullable | Descripción |
|-------|------|----------|-------------|
| id | integer | No | Autoincrement |
| name | string(100) | No | Nombre completo |
| email | string(255) | No | Email único, usado para login |
| password_hash | string(255) | No | Bcrypt hash del password |
| role | string(50) | No | `admin`, `editor`, `viewer` |
| is_active | boolean | No | Default true. Si false, no puede loguearse |
| created_at | datetime | No | UTC |
| updated_at | datetime | No | UTC |

**Constraints:**
- `email` UNIQUE
- `role` solo acepta: `admin`, `editor`, `viewer`
- Password mínimo 8 caracteres (validar en el schema, no en el modelo)

**Seed data:**
El script `seed.py` crea un usuario admin inicial:
- Name: "Admin"
- Email: "admin@configvault.local"
- Password: "admin123"
- Role: "admin"

---

## 4. Matriz de permisos

**Esta es la tabla más importante de todo el proyecto.**

### 4.1 Gestión de usuarios (/api/users)

| Acción | Admin | Editor | Viewer |
|--------|-------|--------|--------|
| Listar usuarios | ✅ | ❌ | ❌ |
| Crear usuario | ✅ | ❌ | ❌ |
| Editar rol de usuario | ✅ | ❌ | ❌ |
| Desactivar usuario | ✅ | ❌ | ❌ |
| Ver propio perfil | ✅ | ✅ | ✅ |
| Cambiar propio password | ✅ | ✅ | ✅ |

### 4.2 Gestión de proyectos (/api/projects)

| Acción | Admin | Editor | Viewer |
|--------|-------|--------|--------|
| Listar proyectos | ✅ | ✅ | ✅ |
| Crear proyecto | ✅ | ✅ | ❌ |
| Editar proyecto | ✅ | ✅ (si es owner) | ❌ |
| Eliminar proyecto | ✅ | ❌ | ❌ |
| Ver detalle | ✅ | ✅ | ✅ |

**Owner**: El usuario que creó el proyecto. Un Editor solo puede editar
proyectos que creó. Un Admin puede editar cualquier proyecto.

### 4.3 Gestión de configuraciones (/api/projects/{id}/configs)

| Acción | Admin | Editor | Viewer |
|--------|-------|--------|--------|
| Listar configs | ✅ | ✅ | ✅ |
| Ver valor de config | ✅ | ✅ | ✅ (excepto secrets) |
| Ver valor de secret | ✅ | ✅ | ❌ (ve ********) |
| Crear config (dev/staging) | ✅ | ✅ | ❌ |
| Editar config (dev/staging) | ✅ | ✅ | ❌ |
| Eliminar config (dev/staging) | ✅ | ✅ | ❌ |
| Crear config (production) | ✅ (directo) | ✅ (requiere aprobación) | ❌ |
| Editar config (production) | ✅ (directo) | ✅ (requiere aprobación) | ❌ |
| Eliminar config (production) | ✅ | ❌ | ❌ |

### 4.4 Aprobaciones (/api/approvals)

| Acción | Admin | Editor | Viewer |
|--------|-------|--------|--------|
| Listar solicitudes pendientes | ✅ | ✅ (solo propias) | ❌ |
| Crear solicitud | ❌ (no la necesita) | ✅ | ❌ |
| Aprobar solicitud | ✅ | ❌ | ❌ |
| Rechazar solicitud | ✅ | ❌ | ❌ |
| Cancelar solicitud | ❌ | ✅ (solo propias) | ❌ |

**Regla crítica**: Un Editor NO puede aprobar sus propias solicitudes.
Solo un Admin puede aprobar.

### 4.5 Audit log (/api/audit)

| Acción | Admin | Editor | Viewer |
|--------|-------|--------|--------|
| Ver log completo | ✅ | ❌ | ❌ |
| Ver log de un proyecto | ✅ | ✅ (proyectos propios) | ✅ (proyectos accesibles) |
| Exportar log | ✅ | ❌ | ❌ |

---

## 5. Implementación de permisos

### Backend: archivo permissions.py

```python
# Estructura sugerida — la implementación exacta según la spec

PERMISSIONS = {
    "admin": {
        "users": ["list", "create", "edit_role", "deactivate"],
        "projects": ["list", "create", "edit", "delete", "view"],
        "configs": ["list", "view", "view_secret", "create", "edit", "delete"],
        "configs_production": ["create_direct", "edit_direct", "delete"],
        "approvals": ["list_all", "approve", "reject"],
        "audit": ["view_all", "export"],
    },
    "editor": {
        "users": [],
        "projects": ["list", "create", "edit_own", "view"],
        "configs": ["list", "view", "view_secret", "create", "edit", "delete"],
        "configs_production": ["create_with_approval", "edit_with_approval"],
        "approvals": ["list_own", "create", "cancel_own"],
        "audit": ["view_project"],
    },
    "viewer": {
        "users": [],
        "projects": ["list", "view"],
        "configs": ["list", "view"],
        "configs_production": [],
        "approvals": [],
        "audit": ["view_project"],
    },
}
```

### Dependency para verificar permisos

```python
def require_permission(resource: str, action: str):
    """
    Dependency que verifica si el usuario actual tiene permiso.
    Uso: Depends(require_permission("configs", "create"))
    Retorna 403 si no tiene permiso.
    """
```

### Frontend: hook usePermissions

```javascript
function usePermissions() {
    // Retorna: { can(action, resource) → boolean }
    // Ejemplo: can("create", "configs") → true/false
    // Usa el rol del usuario del AuthContext
}
```

El frontend usa `can()` para mostrar/ocultar botones y secciones.
El backend SIEMPRE valida — el frontend es solo UX.
