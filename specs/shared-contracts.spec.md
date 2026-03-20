# Especificación: Contratos Compartidos

**Versión:** 1.0  
**Estado:** Draft  

**⚠️ FUENTE DE VERDAD para modelos de datos. Backend y frontend DEBEN respetar estos contratos.**  
**Para roles y permisos, ver auth-and-roles.spec.md**

---

## 1. Modelo: Project

Agrupa configuraciones por aplicación o servicio.

| Campo | Tipo | Nullable | Descripción |
|-------|------|----------|-------------|
| id | integer | No | Autoincrement |
| name | string(100) | No | Nombre del proyecto (único) |
| slug | string(100) | No | Slug URL-safe (único, auto-generado) |
| description | text | Sí | Descripción del proyecto |
| owner_id | integer (FK → users.id) | No | Usuario que lo creó |
| is_archived | boolean | No | Default false |
| created_at | datetime | No | UTC |
| updated_at | datetime | No | UTC |

**Constraints:**
- `name` UNIQUE
- `slug` UNIQUE, generado automáticamente de `name` (lowercase, espacios → guiones)
- ON DELETE del owner: proyecto persiste (el owner_id queda como referencia)

**Ambientes fijos por proyecto:**
Cada proyecto tiene 3 ambientes fijos creados automáticamente al crear el proyecto:
`development`, `staging`, `production`. No se pueden crear ni eliminar ambientes adicionales.

---

## 2. Modelo: Environment

| Campo | Tipo | Nullable | Descripción |
|-------|------|----------|-------------|
| id | integer | No | Autoincrement |
| project_id | integer (FK) | No | Proyecto al que pertenece |
| name | string(50) | No | `development`, `staging`, `production` |
| require_approval | boolean | No | Si true, cambios requieren aprobación |
| created_at | datetime | No | UTC |

**Valores por defecto al crear proyecto:**
- development: `require_approval = false`
- staging: `require_approval = false`
- production: `require_approval = true`

---

## 3. Modelo: ConfigEntry

Una entrada de configuración (variable de entorno, feature flag, o secret).

| Campo | Tipo | Nullable | Descripción |
|-------|------|----------|-------------|
| id | integer | No | Autoincrement |
| environment_id | integer (FK) | No | Ambiente al que pertenece |
| key | string(255) | No | Nombre de la variable (ej: `DATABASE_URL`) |
| value | text | No | Valor (encriptado si type=secret) |
| config_type | string(50) | No | Tipo: `string`, `number`, `boolean`, `json`, `secret`, `feature_flag` |
| description | text | Sí | Descripción opcional |
| is_sensitive | boolean | No | True si type=secret (redundante pero útil para queries) |
| version | integer | No | Se incrementa en cada update (para audit) |
| created_by | integer (FK → users.id) | No | Quién lo creó |
| updated_by | integer (FK → users.id) | No | Quién lo actualizó por última vez |
| created_at | datetime | No | UTC |
| updated_at | datetime | No | UTC |

**Constraints:**
- UNIQUE(environment_id, key) — una key no puede repetirse en el mismo ambiente
- `config_type` solo acepta: `string`, `number`, `boolean`, `json`, `secret`, `feature_flag`
- Si `config_type = secret`: el valor se encripta con Fernet antes de guardar en DB
- Si `config_type = feature_flag`: el valor debe ser `"true"` o `"false"`
- Si `config_type = number`: el valor debe ser un número válido
- Si `config_type = boolean`: el valor debe ser `"true"` o `"false"`
- Si `config_type = json`: el valor debe ser JSON válido

---

## 4. Modelo: ApprovalRequest

Solicitud de aprobación para cambios en ambientes con `require_approval = true`.

| Campo | Tipo | Nullable | Descripción |
|-------|------|----------|-------------|
| id | integer | No | Autoincrement |
| config_entry_id | integer (FK) | Sí | Config existente (null si es nuevo) |
| environment_id | integer (FK) | No | Ambiente destino |
| action | string(50) | No | `create`, `update`, `delete` |
| key | string(255) | No | Key de la config |
| proposed_value | text | Sí | Valor propuesto (null si delete) |
| config_type | string(50) | No | Tipo de la config |
| current_value | text | Sí | Valor actual (null si create) |
| status | string(50) | No | Estado de la solicitud |
| requested_by | integer (FK → users.id) | No | Quién solicitó |
| reviewed_by | integer (FK → users.id) | Sí | Quién aprobó/rechazó |
| review_comment | text | Sí | Comentario del reviewer |
| created_at | datetime | No | UTC |
| reviewed_at | datetime | Sí | Cuándo se revisó |

### Diagrama de estados de ApprovalRequest

```
       ┌──────────┐
       │ pending  │
       └────┬─────┘
            │
     ┌──────┼──────┐
     │      │      │
     ▼      ▼      ▼
┌────────┐ ┌────────┐ ┌───────────┐
│approved│ │rejected│ │ cancelled │
└───┬────┘ └────────┘ └───────────┘
    │
    ▼ (cambio se aplica automáticamente)
 [Config creada/actualizada/eliminada]
```

**Valores de status:** `pending`, `approved`, `rejected`, `cancelled`

**Comportamiento al aprobar:**
1. `status` cambia a `approved`
2. `reviewed_by` se setea al admin que aprobó
3. `reviewed_at` se setea a UTC now
4. El cambio se aplica automáticamente:
   - Si action=create: se crea la ConfigEntry
   - Si action=update: se actualiza la ConfigEntry
   - Si action=delete: se elimina la ConfigEntry
5. Se genera entrada de audit log

---

## 5. Modelo: AuditLog

Registra CADA acción que modifica datos en el sistema.

| Campo | Tipo | Nullable | Descripción |
|-------|------|----------|-------------|
| id | integer | No | Autoincrement |
| user_id | integer (FK → users.id) | No | Quién hizo la acción |
| action | string(50) | No | Tipo de acción |
| resource_type | string(50) | No | Tipo de recurso afectado |
| resource_id | integer | Sí | ID del recurso afectado |
| project_id | integer (FK) | Sí | Proyecto relacionado (para filtrar) |
| details | text (JSON) | No | Detalle de la acción en JSON |
| ip_address | string(45) | Sí | IP del cliente |
| created_at | datetime | No | UTC |

### Acciones de auditoría

| action | resource_type | Cuándo |
|--------|--------------|--------|
| `login` | user | Login exitoso |
| `logout` | user | Logout |
| `login_failed` | user | Intento fallido |
| `user_created` | user | Admin crea usuario |
| `user_updated` | user | Cambio de rol/estado |
| `project_created` | project | Nuevo proyecto |
| `project_updated` | project | Edición de proyecto |
| `project_deleted` | project | Eliminación |
| `config_created` | config | Nueva config (directa o post-aprobación) |
| `config_updated` | config | Edición de config |
| `config_deleted` | config | Eliminación de config |
| `approval_requested` | approval | Editor solicita aprobación |
| `approval_approved` | approval | Admin aprueba |
| `approval_rejected` | approval | Admin rechaza |
| `approval_cancelled` | approval | Editor cancela su solicitud |
| `secret_accessed` | config | Alguien ve un valor secret desencriptado |

**El campo `details` es JSON con contexto específico:**
```json
// Ejemplo para config_updated:
{
  "key": "DATABASE_URL",
  "environment": "staging",
  "old_value": "postgres://old...",
  "new_value": "postgres://new...",
  "config_type": "string",
  "version": 3
}

// Ejemplo para secret: NUNCA incluir el valor
{
  "key": "API_SECRET_KEY",
  "environment": "production",
  "config_type": "secret",
  "note": "value changed (not logged for security)"
}
```

---

## 6. Schemas JSON (contratos de response)

### UserResponse

```json
{
  "id": 1,
  "name": "Admin User",
  "email": "admin@configvault.local",
  "role": "admin",
  "is_active": true,
  "created_at": "2026-03-17T10:00:00Z"
}
```

**Nota:** NUNCA incluir `password_hash` en responses.

### ProjectResponse

```json
{
  "id": 1,
  "name": "Web Application",
  "slug": "web-application",
  "description": "Main web app configs",
  "owner": {
    "id": 2,
    "name": "Editor User",
    "email": "editor@configvault.local"
  },
  "environments": [
    { "id": 1, "name": "development", "require_approval": false, "config_count": 12 },
    { "id": 2, "name": "staging", "require_approval": false, "config_count": 10 },
    { "id": 3, "name": "production", "require_approval": true, "config_count": 8 }
  ],
  "is_archived": false,
  "created_at": "2026-03-17T10:00:00Z",
  "updated_at": "2026-03-17T10:00:00Z"
}
```

### ConfigEntryResponse

```json
{
  "id": 1,
  "key": "DATABASE_URL",
  "value": "postgres://localhost:5432/mydb",
  "config_type": "string",
  "description": "Database connection string",
  "is_sensitive": false,
  "version": 2,
  "created_by": { "id": 2, "name": "Editor User" },
  "updated_by": { "id": 1, "name": "Admin User" },
  "created_at": "2026-03-17T10:00:00Z",
  "updated_at": "2026-03-17T11:00:00Z"
}
```

**Para secrets, cuando el usuario es Viewer:**
```json
{
  "id": 5,
  "key": "API_SECRET_KEY",
  "value": "********",
  "config_type": "secret",
  "is_sensitive": true,
  ...
}
```

### ApprovalRequestResponse

```json
{
  "id": 1,
  "config_entry_id": null,
  "environment": { "id": 3, "name": "production" },
  "project": { "id": 1, "name": "Web Application" },
  "action": "create",
  "key": "NEW_API_KEY",
  "proposed_value": "sk-abc123",
  "config_type": "secret",
  "current_value": null,
  "status": "pending",
  "requested_by": { "id": 2, "name": "Editor User" },
  "reviewed_by": null,
  "review_comment": null,
  "created_at": "2026-03-17T12:00:00Z",
  "reviewed_at": null
}
```

**Nota:** `proposed_value` para secrets se muestra como `"********"` para viewers.

### AuditLogResponse

```json
{
  "id": 1,
  "user": { "id": 1, "name": "Admin User" },
  "action": "config_updated",
  "resource_type": "config",
  "resource_id": 5,
  "project": { "id": 1, "name": "Web Application" },
  "details": { "key": "DATABASE_URL", "environment": "staging", ... },
  "ip_address": "127.0.0.1",
  "created_at": "2026-03-17T11:30:00Z"
}
```

### ErrorResponse (mismo formato de proyectos anteriores)

```json
{
  "detail": {
    "code": "FORBIDDEN",
    "message": "You don't have permission to edit production configs directly",
    "field": null
  }
}
```

### Códigos de error adicionales para este proyecto

| code | Cuándo |
|------|--------|
| `INVALID_CREDENTIALS` | Login con email/password incorrectos |
| `TOKEN_REQUIRED` | Request sin header Authorization |
| `TOKEN_EXPIRED` | JWT expirado |
| `INVALID_TOKEN` | JWT inválido o malformado |
| `TOKEN_REVOKED` | JWT en blacklist (post-logout) |
| `FORBIDDEN` | Usuario autenticado pero sin permiso |
| `APPROVAL_REQUIRED` | Editor intenta modificar production directamente |
| `INVALID_STATE_TRANSITION` | Acción no válida para el estado actual |
| `DUPLICATE_RESOURCE` | Key duplicada en mismo ambiente |
| `INVALID_CONFIG_VALUE` | Valor no coincide con config_type |

---

## 7. Colores y UI por rol

| Rol | Color badge | Icono sugerido |
|-----|-------------|----------------|
| admin | `#7C3AED` (purple-600) | 🛡️ |
| editor | `#2563EB` (blue-600) | ✏️ |
| viewer | `#6B7280` (gray-500) | 👁️ |

| Config type | Color | Icono |
|-------------|-------|-------|
| string | `#6B7280` (gray) | Aa |
| number | `#2563EB` (blue) | # |
| boolean | `#8B5CF6` (purple) | ⊘ |
| json | `#F59E0B` (amber) | {} |
| secret | `#EF4444` (red) | 🔒 |
| feature_flag | `#10B981` (green) | 🚩 |
