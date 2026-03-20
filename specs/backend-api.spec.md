# Especificación: Backend API

**Versión:** 1.0  
**Estado:** Draft  
**Base URL:** `http://localhost:8000`  
**Auth:** Ver `auth-and-roles.spec.md`  
**Modelos:** Ver `shared-contracts.spec.md`

**Todos los endpoints (excepto login) requieren header:**
`Authorization: Bearer <access_token>`

---

## Fase 1 — Auth + Users

### POST /api/auth/login

**Auth requerida:** No

**Request:**
```json
{ "email": "admin@configvault.local", "password": "admin123" }
```

**Response 200:**
```json
{
  "access_token": "eyJhbG...",
  "token_type": "bearer",
  "user": { "id": 1, "name": "Admin", "email": "admin@configvault.local", "role": "admin" }
}
```

Genera audit log: `login` (o `login_failed` si falla)

---

### POST /api/auth/logout

**Auth requerida:** Sí (cualquier rol)

**Comportamiento:** Agrega el token actual a la blacklist en Redis con TTL = tiempo restante.

**Response 200:** `{ "message": "Logged out successfully" }`

---

### GET /api/auth/me

**Auth requerida:** Sí (cualquier rol)

**Response 200:** `UserResponse` del usuario actual

---

### PUT /api/auth/me/password

**Auth requerida:** Sí (cualquier rol)

**Request:**
```json
{ "current_password": "old123", "new_password": "new12345" }
```

**Validaciones:**
- `current_password` debe ser correcto
- `new_password` mínimo 8 caracteres
- `new_password` no puede ser igual a `current_password`

**Response 200:** `{ "message": "Password updated successfully" }`

---

### GET /api/users (Admin only)

**Auth requerida:** Admin

**Query params:** `page`, `per_page`, `role`, `is_active`, `search` (busca en name/email)

**Response 200:** `{ data: [UserResponse], pagination: {...} }`

---

### POST /api/users (Admin only)

**Auth requerida:** Admin

**Request:**
```json
{
  "name": "New User",
  "email": "new@example.com",
  "password": "password123",
  "role": "editor"
}
```

**Response 201:** `UserResponse`

Genera audit log: `user_created`

---

### PUT /api/users/{id} (Admin only)

**Auth requerida:** Admin

**Request (campos opcionales):**
```json
{ "name": "Updated Name", "role": "viewer", "is_active": false }
```

**Reglas:**
- Admin no puede desactivarse a sí mismo
- Admin no puede cambiar su propio rol
- No se puede cambiar email (inmutable)

**Response 200:** `UserResponse`

Genera audit log: `user_updated`

**Criterios de aceptación Fase 1:**
- [ ] Login devuelve JWT válido
- [ ] JWT se verifica correctamente en endpoints protegidos
- [ ] Token expirado → 401
- [ ] Logout agrega token a blacklist en Redis
- [ ] CRUD de users funciona solo para Admin
- [ ] Editor/Viewer reciben 403 en endpoints de users
- [ ] Cambio de password funciona con validaciones
- [ ] Audit log registra login/logout/login_failed
- [ ] seed.py crea usuario admin correctamente
- [ ] Tests con usuarios de cada rol

---

## Fase 2 — Projects + Environments

### POST /api/projects

**Auth:** Admin, Editor

**Request:**
```json
{
  "name": "Web Application",
  "description": "Main web app configurations"
}
```

**Comportamiento:**
1. Generar `slug` a partir de `name`
2. Setear `owner_id` al usuario actual
3. Crear automáticamente 3 environments: development, staging, production
4. production tiene `require_approval = true`

**Response 201:** `ProjectResponse` (con environments incluidos)

---

### GET /api/projects

**Auth:** Cualquier rol

**Query params:** `page`, `per_page`, `search`, `is_archived`

**Response 200:** `{ data: [ProjectResponse], pagination: {...} }`

---

### GET /api/projects/{id}

**Auth:** Cualquier rol

**Response 200:** `ProjectResponse`

---

### PUT /api/projects/{id}

**Auth:** Admin (cualquier proyecto), Editor (solo si es owner)

**Request:** `{ "name": "...", "description": "...", "is_archived": true }`

**Response 200:** `ProjectResponse`

---

### DELETE /api/projects/{id}

**Auth:** Admin only

**Comportamiento:** Elimina proyecto + environments + configs + approvals (CASCADE)

**Response 204**

**Criterios de aceptación Fase 2:**
- [ ] Crear proyecto auto-genera 3 environments
- [ ] Editor solo puede editar sus propios proyectos
- [ ] Viewer no puede crear ni editar
- [ ] Admin puede editar cualquier proyecto
- [ ] Solo Admin puede eliminar proyectos
- [ ] Slug se genera correctamente
- [ ] Tests de permisos por rol

---

## Fase 3 — ConfigEntries + Feature Flags + Secrets

### GET /api/projects/{project_id}/environments/{env_id}/configs

**Auth:** Cualquier rol

**Query params:** `config_type`, `search` (busca en key/description)

**Response 200:** Array de `ConfigEntryResponse`

**Nota:** Si el usuario es Viewer, los secrets muestran `value: "********"`

---

### POST /api/projects/{project_id}/environments/{env_id}/configs

**Auth:** Admin, Editor

**Request:**
```json
{
  "key": "DATABASE_URL",
  "value": "postgres://localhost:5432/mydb",
  "config_type": "string",
  "description": "Database connection"
}
```

**Comportamiento para environments CON require_approval:**
- Si el usuario es **Admin**: se crea directamente
- Si el usuario es **Editor**: se crea un `ApprovalRequest` con action=`create` en vez de crear la config directamente. Response cambia:

**Response para Editor en production:**
```
HTTP 202 Accepted

{
  "message": "Approval request created",
  "approval_request": { ...ApprovalRequestResponse... }
}
```

**Validaciones de valor según tipo:**
- `string`: cualquier valor
- `number`: debe ser número válido (int o float)
- `boolean`: solo `"true"` o `"false"`
- `json`: debe ser JSON válido
- `secret`: cualquier valor (se encripta al guardar)
- `feature_flag`: solo `"true"` o `"false"`

**Response directa 201:** `ConfigEntryResponse`

---

### PUT /api/projects/{project_id}/environments/{env_id}/configs/{config_id}

**Auth:** Admin, Editor

**Request:**
```json
{ "value": "new-value", "description": "Updated description" }
```

**Comportamiento:**
- Incrementa `version`
- Actualiza `updated_by` y `updated_at`
- Si environment tiene `require_approval` y usuario es Editor → crea ApprovalRequest (202)
- Si secret: encriptar nuevo valor

---

### DELETE /api/projects/{project_id}/environments/{env_id}/configs/{config_id}

**Auth:** Admin (cualquier env), Editor (solo dev/staging)

**Response 204**

---

### POST /api/projects/{project_id}/environments/{env_id}/configs/{config_id}/reveal

**Auth:** Admin, Editor (Viewer → 403)

Endpoint especial para obtener el valor desencriptado de un secret.

**Response 200:**
```json
{ "value": "the-actual-secret-value" }
```

Genera audit log: `secret_accessed`

---

### PUT /api/projects/{project_id}/environments/{env_id}/configs/{config_id}/toggle

**Auth:** Admin, Editor

Atajo para toggle de feature flags. Solo funciona si `config_type = feature_flag`.

**Comportamiento:** Cambia `"true"` → `"false"` o viceversa

**Si environment con approval:** genera ApprovalRequest

**Response 200:** `ConfigEntryResponse`

**Criterios de aceptación Fase 3:**
- [ ] CRUD de configs funciona en dev/staging para Admin y Editor
- [ ] Configs en production generan ApprovalRequest para Editor (202)
- [ ] Configs en production se crean directo para Admin (201)
- [ ] Secrets se encriptan en DB y desencriptan en response
- [ ] Viewer ve `********` para secrets
- [ ] Reveal genera audit log
- [ ] Feature flag toggle funciona
- [ ] Validación de tipos (number, boolean, json) funciona
- [ ] Key duplicada en mismo ambiente → 409
- [ ] Tests exhaustivos por tipo y por rol

---

## Fase 4 — Approval Flow

### GET /api/approvals

**Auth:** Admin (ve todas), Editor (solo las propias)

**Query params:** `status`, `project_id`, `page`, `per_page`

**Response 200:** `{ data: [ApprovalRequestResponse], pagination: {...} }`

---

### GET /api/approvals/{id}

**Auth:** Admin, Editor (solo si es el solicitante)

**Response 200:** `ApprovalRequestResponse`

---

### POST /api/approvals/{id}/approve

**Auth:** Admin only

**Request:**
```json
{ "comment": "Looks good, approved." }
```

**Comportamiento:**
1. Validar que status sea `pending`
2. Cambiar status a `approved`
3. Setear `reviewed_by`, `reviewed_at`, `review_comment`
4. **Aplicar el cambio automáticamente:**
   - Si action=`create`: crear la ConfigEntry
   - Si action=`update`: actualizar la ConfigEntry
   - Si action=`delete`: eliminar la ConfigEntry
5. Generar audit logs: `approval_approved` + `config_created/updated/deleted`

**Response 200:** `ApprovalRequestResponse` actualizado

---

### POST /api/approvals/{id}/reject

**Auth:** Admin only

**Request:**
```json
{ "comment": "Value seems incorrect, please verify." }
```

**Comportamiento:**
1. Validar que status sea `pending`
2. Cambiar status a `rejected`
3. Setear reviewed_by, reviewed_at, review_comment
4. NO se aplica ningún cambio
5. Generar audit log: `approval_rejected`

**Response 200:** `ApprovalRequestResponse` actualizado

---

### POST /api/approvals/{id}/cancel

**Auth:** Editor (solo sus propias solicitudes)

**Comportamiento:**
1. Validar que status sea `pending`
2. Validar que `requested_by` sea el usuario actual
3. Cambiar status a `cancelled`

**Response 200:** `ApprovalRequestResponse` actualizado

**Criterios de aceptación Fase 4:**
- [ ] Editor crea approval al modificar production
- [ ] Admin puede aprobar → cambio se aplica automáticamente
- [ ] Admin puede rechazar → cambio NO se aplica
- [ ] Editor puede cancelar sus propias solicitudes pendientes
- [ ] No se puede aprobar/rechazar solicitudes ya procesadas (409)
- [ ] Editor NO puede aprobar (ni las ajenas ni las propias)
- [ ] Audit logs se generan para cada acción de aprobación
- [ ] Tests para el flujo completo: solicitar → aprobar → verificar config creada

---

## Fase 5 — Audit Log + Redis Cache

### GET /api/audit

**Auth:** Admin (log completo)

**Query params:** `page`, `per_page`, `action`, `resource_type`, `user_id`, `project_id`, `date_from`, `date_to`

**Response 200:** `{ data: [AuditLogResponse], pagination: {...} }`

---

### GET /api/audit/export

**Auth:** Admin only

**Query params:** mismos filtros que GET /api/audit

**Response 200:** CSV file download

```csv
timestamp,user,action,resource_type,resource_id,project,details
2026-03-17T10:00:00Z,Admin User,config_updated,config,5,Web Application,"{""key"":""DB_URL""}"
```

---

### GET /api/projects/{project_id}/audit

**Auth:** Admin (todo), Editor (si es owner), Viewer (si puede ver el proyecto)

Audit log filtrado por proyecto.

**Response 200:** `{ data: [AuditLogResponse], pagination: {...} }`

---

### Redis Cache (app/cache.py)

**Qué se cachea:**
1. **Configs por ambiente:** key = `configs:{project_id}:{env_id}`, TTL = 5 min
2. **Dashboard stats:** key = `dashboard:stats`, TTL = 1 min
3. **Token blacklist:** key = `blacklist:{token_jti}`, TTL = tiempo restante del token

**Invalidación:**
- Cuando se crea/edita/elimina una config → invalidar `configs:{project_id}:{env_id}`
- Cuando se aprueba un approval → invalidar configs del ambiente afectado
- Dashboard stats se invalida por TTL (no activamente)

**Fallback:**
- Si Redis no está disponible → queries directos a SQLite (sin cache)
- NUNCA fallar un request porque Redis esté caído

```python
class CacheManager:
    async def get(self, key: str) -> str | None: ...
    async def set(self, key: str, value: str, ttl: int = 300) -> None: ...
    async def delete(self, key: str) -> None: ...
    async def is_blacklisted(self, token_jti: str) -> bool: ...
    async def blacklist_token(self, token_jti: str, ttl: int) -> None: ...
```

**Criterios de aceptación Fase 5:**
- [ ] Audit log registra TODAS las acciones de las fases anteriores
- [ ] Admin puede filtrar audit por acción, usuario, proyecto, fechas
- [ ] Export CSV funciona con filtros
- [ ] Editor y Viewer ven audit solo de sus proyectos
- [ ] Redis cache funciona para configs (hit/miss verificable en logs)
- [ ] Cache se invalida al modificar configs
- [ ] Sistema funciona si Redis está caído (fallback a DB)
- [ ] Token blacklist funciona (logout → token rechazado)
- [ ] Tests para audit log (verificar que cada acción genera log)
- [ ] Tests para cache (mock Redis)
