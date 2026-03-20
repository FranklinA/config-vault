# Prompts para Claude Code — Proyecto 4

---

## Sesión 1: Backend Auth (Fase 1)

```bash
cd config-vault/backend
claude
```

### Fase 1 — Auth + Users

#### Prompt 1.1: Setup base + modelos
```
Lee CLAUDE.md, specs/auth-and-roles.spec.md, y specs/shared-contracts.spec.md.
Implementa:
1. app/config.py con settings (JWT secret, Redis URL, DB URL, Fernet key)
2. app/database.py con engine async SQLite
3. app/models.py con TODOS los modelos: User, Project, Environment, ConfigEntry, ApprovalRequest, AuditLog
4. app/schemas.py con todos los Pydantic schemas
5. app/main.py con FastAPI app y lifespan

NO implementes endpoints aún, solo la estructura base.
```

#### Prompt 1.2: Security + Auth
```
Lee la sección 1 de specs/auth-and-roles.spec.md.
Implementa:
1. app/security.py: JWT encode/decode, password hashing (bcrypt), token verification
2. app/dependencies.py: get_db, get_current_user (extrae user del JWT), require_role(role)
3. app/cache.py: CacheManager con Redis (connect, get, set, delete, blacklist_token, is_blacklisted)
   - Debe funcionar sin Redis (fallback silencioso)
4. app/permissions.py: la matriz de permisos y función require_permission()
5. app/audit.py: función create_audit_log() que registra acciones
6. seed.py: script que crea el usuario admin inicial

Ejecuta seed.py y verifica que el usuario se crea.
```

#### Prompt 1.3: Auth endpoints
```
Lee la Fase 1 de specs/backend-api.spec.md.
Implementa app/routers/auth.py y app/routers/users.py:
- POST /api/auth/login
- POST /api/auth/logout
- GET /api/auth/me
- PUT /api/auth/me/password
- GET /api/users (admin only)
- POST /api/users (admin only)
- PUT /api/users/{id} (admin only)

Registra los routers en main.py.
Todos los endpoints de users deben usar require_role("admin").
```

#### Prompt 1.4: Verificar auth
```
Inicia el servidor y prueba:
1. POST /api/auth/login con admin@configvault.local / admin123 → token
2. GET /api/auth/me con el token → datos del admin
3. POST /api/users (crear un editor y un viewer)
4. POST /api/auth/login como editor → token de editor
5. GET /api/users con token de editor → debe dar 403
6. POST /api/auth/logout con token de admin
7. GET /api/auth/me con el token revocado → debe dar 401

Muéstrame status y body de cada paso.
```

#### Prompt 1.5: Tests auth
```
Crea tests/conftest.py con fixtures:
- test_db (SQLite en memoria)
- test_client (AsyncClient)
- admin_user, editor_user, viewer_user (pre-creados)
- admin_token, editor_token, viewer_token (JWTs válidos)
- mock_redis (o fakeredis)

Crea tests/test_auth.py y tests/test_users.py.
Cada test de permisos debe probar los 3 roles.
Ejecuta los tests.
```

---

## Sesión 2: Backend Core (Fases 2-5)

#### Prompt 2.1: Projects + Environments
```
Lee la Fase 2 de specs/backend-api.spec.md.
Implementa app/routers/projects.py:
- POST /api/projects (auto-crea 3 environments)
- GET /api/projects (con paginación)
- GET /api/projects/{id}
- PUT /api/projects/{id} (admin=cualquiera, editor=solo propios)
- DELETE /api/projects/{id} (admin only)

Cada operación que modifica datos debe generar audit log.
```

#### Prompt 2.2: Verificar projects
```
Con 3 usuarios (admin, editor, viewer), prueba:
1. Editor crea proyecto "My App" → 201
2. Editor crea otro proyecto "Backend API" → 201
3. Viewer intenta crear proyecto → 403
4. GET /api/projects como viewer → ve ambos
5. Editor intenta editar "My App" (su proyecto) → 200
6. Editor intenta editar "Backend API" del admin → 403
7. Admin edita "Backend API" → 200
8. Viewer intenta eliminar → 403
9. Editor intenta eliminar → 403
10. Admin elimina → 204
```

#### Prompt 3.1: ConfigEntries + Secrets + Feature Flags
```
Lee la Fase 3 de specs/backend-api.spec.md.
Implementa:
1. app/encryption.py: Fernet encrypt/decrypt para secrets
2. app/routers/configs.py con TODOS los endpoints de configs:
   - GET configs (con filtros)
   - POST config (directo o via approval según ambiente y rol)
   - PUT config
   - DELETE config
   - POST reveal (desencriptar secret)
   - PUT toggle (feature flag)
3. Lógica de approval: si Editor + production → crear ApprovalRequest (202)
4. Validación de tipos (number, boolean, json, etc.)
5. Secrets se encriptan en DB, se desencriptan en response (excepto para Viewer)
```

#### Prompt 3.2: Verificar configs
```
Prueba con los 3 roles:
1. Editor crea configs en development: DB_URL (string), DEBUG (boolean), API_KEY (secret)
2. Viewer lee configs → ve ******** para API_KEY
3. Editor intenta reveal de API_KEY → 200 con valor real
4. Viewer intenta reveal → 403
5. Editor crea feature flag ENABLE_CACHE en staging
6. Editor toggle ENABLE_CACHE → cambia de true a false
7. Editor crea config en production → debe recibir 202 (approval)
8. Admin crea config en production → debe recibir 201 (directo)
9. Editor intenta eliminar config de production → 403
```

#### Prompt 4.1: Approval flow
```
Lee la Fase 4 de specs/backend-api.spec.md.
Implementa app/routers/approvals.py:
- GET /api/approvals (admin=todas, editor=propias)
- GET /api/approvals/{id}
- POST /api/approvals/{id}/approve (admin only, aplica cambio)
- POST /api/approvals/{id}/reject (admin only)
- POST /api/approvals/{id}/cancel (editor, solo propias)

Al aprobar, el cambio (create/update/delete) se aplica automáticamente.
Genera audit logs para cada acción.
```

#### Prompt 4.2: Verificar approval flow
```
Flujo completo:
1. Editor crea config PROD_DB en production → 202 (approval pending)
2. GET /api/approvals como editor → ve su solicitud
3. GET /api/approvals como admin → ve la solicitud
4. Admin aprueba con comentario "Looks good"
5. GET configs de production → PROD_DB existe con el valor correcto
6. Verificar audit log: approval_requested + approval_approved + config_created

Flujo de rechazo:
7. Editor crea otra config en production → approval pending
8. Admin rechaza con comentario "Wrong value"
9. Config NO aparece en production
10. Editor ve el rechazo con comentario
```

#### Prompt 5.1: Audit log + Redis cache
```
Lee la Fase 5 de specs/backend-api.spec.md.
Implementa:
1. app/routers/audit.py:
   - GET /api/audit (admin, con filtros completos)
   - GET /api/audit/export (CSV download)
   - GET /api/projects/{id}/audit (filtrado por proyecto)
2. Redis cache en app/cache.py (si no está implementado):
   - Cache de configs por ambiente
   - Invalidación al modificar
   - Fallback si Redis no disponible
3. Middleware de audit en app/middleware/audit_middleware.py

Verifica que TODAS las acciones de fases anteriores generaron audit logs.
```

#### Prompt 5.2: Tests completos backend
```
Crea/completa tests para:
- tests/test_projects.py: CRUD + permisos por rol
- tests/test_configs.py: CRUD + tipos + secrets + feature flags + approval redirect
- tests/test_approvals.py: flujo completo approve/reject/cancel
- tests/test_audit.py: verificar que cada acción genera log
- tests/test_permissions.py: test EXHAUSTIVO de la matriz de permisos
  (cada combinación rol × recurso × acción)
- tests/test_encryption.py: encrypt/decrypt de secrets

Ejecuta toda la suite y muéstrame resultados.
```

---

## Sesión 3: Frontend (Fase 6)

```bash
cd config-vault/frontend
claude
```

#### Prompt 6.0: Setup
```
Lee CLAUDE.md (sección frontend).
Inicializa React con Vite:
- npm create vite@latest . -- --template react
- Instala react-router-dom
- Configura proxy en vite.config.js para /api → localhost:8000
- Crea estructura de carpetas según CLAUDE.md
- Crea variables CSS (:root) con colores de roles y config types
- Crea utils/api.js con fetch wrapper que auto-inyecta Bearer token
- Crea utils/permissions.js con la misma matriz del backend
```

#### Prompt 6.1: Auth (Login + Context + ProtectedRoute)
```
Lee secciones 6.1-6.4 de specs/frontend-ui.spec.md.
Implementa:
1. AuthContext con login, logout, user, token
2. LoginForm con validación y error display
3. ProtectedRoute que verifica auth + rol
4. Layout con Header (user info + logout) y Sidebar (items por rol)
5. Hook usePermissions con can(action, resource)
```

#### Prompt 6.2: Projects + Configs
```
Lee secciones 6.5-6.6 de specs/frontend-ui.spec.md.
Implementa:
1. ProjectList con cards y botón crear
2. ProjectDetail con EnvironmentTabs
3. ConfigTable con iconos por tipo y acciones por permiso
4. ConfigEditor modal (adaptar input por tipo)
5. SecretField con reveal (👁)
6. FeatureFlagToggle
7. Warning de approval en production
```

#### Prompt 6.3: Approvals
```
Lee secciones 6.7-6.8 de specs/frontend-ui.spec.md.
Implementa:
1. ApprovalList con filtro por status
2. ApprovalDetail con diff actual vs propuesto
3. Botones Approve/Reject (admin) y Cancel (editor)
4. Comment field para approve/reject
```

#### Prompt 6.4: Users + Audit + Notifications
```
Lee secciones 6.9-6.11 de specs/frontend-ui.spec.md.
Implementa:
1. UserManagement (tabla + crear + editar rol + toggle active)
2. AuditLog con filtros y paginación
3. Export CSV button
4. NotificationContext con toasts
```

---

## Sesión 4: Integración (Fase 7)

#### Prompt 7.1: Test multi-rol end-to-end
```
Lee la Fase 7 de specs/frontend-ui.spec.md.
Con backend y frontend corriendo, ejecuta los 4 escenarios:

Escenario 1: Flujo Editor (crear proyecto → configs → approval → aprobación)
Escenario 2: Viewer (solo lectura, secrets ocultos, sin botones de acción)
Escenario 3: Admin (gestión total, audit, export)
Escenario 4: Approval rechazada (config no se crea)

Lista TODOS los problemas encontrados.
```

#### Prompt 7.2: README
```
Genera README.md con:
- Descripción y arquitectura
- Setup (Docker para Redis, backend, frontend, seed)
- Roles y permisos (tabla resumen)
- API endpoints con ejemplos curl autenticados
- Flujo de aprobación explicado
- Estructura del proyecto
- Cómo ejecutar tests
```

---

## 🔑 Tips para Proyecto 4

- **La matriz de permisos es tu brújula.** Si algo no funciona, revisa primero
  auth-and-roles.spec.md. El 80% de los bugs en este proyecto son de permisos.

- **Testea con los 3 roles SIEMPRE.** Cada endpoint debe probarse como admin,
  editor, y viewer. Si un test solo prueba con admin, no prueba nada útil.

- **Secrets nunca en logs.** Si descubres un secret en texto plano en el audit
  log o en un error response, eso es un bug de seguridad que tu spec debe
  prevenir explícitamente.

- **El flujo de aprobación es una máquina de estados.** Cada transición inválida
  (ej: aprobar algo ya rechazado) debe estar cubierta en la spec y en los tests.
