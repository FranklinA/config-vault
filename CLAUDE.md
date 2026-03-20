# CLAUDE.md — Config Vault

## Descripción del proyecto

Sistema de gestión de configuración para aplicaciones. Permite a equipos
gestionar variables de entorno, feature flags, y secrets organizados por
proyecto y ambiente (dev/staging/production). Incluye control de acceso
basado en roles, flujo de aprobación para cambios en producción, y
registro de auditoría de todas las acciones.

## Stack tecnológico

### Backend
- Lenguaje: Python 3.11+
- Framework: FastAPI
- ORM: SQLAlchemy 2.0 (async)
- Base de datos: SQLite (vía aiosqlite)
- Cache: Redis (vía redis-py async)
- Auth: JWT (PyJWT) + bcrypt para password hashing
- Encriptación de secrets: cryptography (Fernet)
- Testing: pytest + pytest-asyncio + httpx

### Frontend
- Framework: React 18
- Build tool: Vite
- Lenguaje: JavaScript (JSX)
- Estilos: CSS Modules
- HTTP client: fetch nativo con interceptor de auth
- Estado: React Context + useReducer
- Routing: React Router v6

### Infraestructura
- Redis: cache de configs + blacklist de tokens revocados
- SQLite: datos persistentes

## Estructura del proyecto

```
config-vault/
├── CLAUDE.md
├── specs/
│   ├── auth-and-roles.spec.md
│   ├── shared-contracts.spec.md
│   ├── backend-api.spec.md
│   └── frontend-ui.spec.md
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── config.py                  # Settings (JWT secret, Redis URL, etc.)
│   │   ├── database.py
│   │   ├── models.py
│   │   ├── schemas.py
│   │   ├── security.py                # JWT encode/decode, password hashing
│   │   ├── encryption.py              # Fernet encrypt/decrypt para secrets
│   │   ├── permissions.py             # Verificación de permisos por rol
│   │   ├── audit.py                   # Logger de auditoría
│   │   ├── cache.py                   # Redis cache helpers
│   │   ├── dependencies.py            # get_db, get_current_user, require_role
│   │   ├── routers/
│   │   │   ├── __init__.py
│   │   │   ├── auth.py                # /api/auth/*
│   │   │   ├── users.py               # /api/users/*
│   │   │   ├── projects.py            # /api/projects/*
│   │   │   ├── configs.py             # /api/projects/{id}/configs/*
│   │   │   ├── approvals.py           # /api/approvals/*
│   │   │   └── audit.py               # /api/audit/*
│   │   └── middleware/
│   │       └── audit_middleware.py     # Middleware que registra cada request
│   ├── tests/
│   │   ├── __init__.py
│   │   ├── conftest.py                # Fixtures: users por rol, test db, mock redis
│   │   ├── test_auth.py
│   │   ├── test_users.py
│   │   ├── test_projects.py
│   │   ├── test_configs.py
│   │   ├── test_approvals.py
│   │   ├── test_audit.py
│   │   ├── test_permissions.py        # Tests exhaustivos de la matriz de permisos
│   │   └── test_encryption.py
│   ├── seed.py                        # Script para crear usuario admin inicial
│   └── requirements.txt
├── frontend/
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js
│   └── src/
│       ├── main.jsx
│       ├── App.jsx
│       ├── context/
│       │   ├── AuthContext.jsx         # Auth state + JWT management
│       │   └── NotificationContext.jsx # Toast notifications
│       ├── hooks/
│       │   ├── useAuth.js
│       │   └── usePermissions.js       # Hook que expone can(action, resource)
│       ├── components/
│       │   ├── layout/
│       │   │   ├── Header.jsx
│       │   │   ├── Sidebar.jsx
│       │   │   └── ProtectedRoute.jsx  # Redirect si no autenticado
│       │   ├── auth/
│       │   │   ├── LoginForm.jsx
│       │   │   └── UserManagement.jsx  # Solo admin
│       │   ├── projects/
│       │   │   ├── ProjectList.jsx
│       │   │   ├── ProjectDetail.jsx
│       │   │   └── EnvironmentTabs.jsx
│       │   ├── configs/
│       │   │   ├── ConfigTable.jsx
│       │   │   ├── ConfigEditor.jsx    # Modal crear/editar
│       │   │   ├── SecretField.jsx     # Campo con show/hide
│       │   │   └── FeatureFlagToggle.jsx
│       │   ├── approvals/
│       │   │   ├── ApprovalList.jsx
│       │   │   ├── ApprovalDetail.jsx
│       │   │   └── ApprovalActions.jsx
│       │   └── audit/
│       │       ├── AuditLog.jsx
│       │       └── AuditEntry.jsx
│       └── utils/
│           ├── api.js                  # Fetch wrapper con JWT auto-inject
│           ├── constants.js
│           └── permissions.js          # Misma matriz del backend (para UI)
├── docker-compose.yml                  # Redis service
├── .gitignore
└── README.md
```

## Convenciones de código

### Backend (Python)
- Mismas convenciones del Proyecto 2 y 3
- TODOS los endpoints requieren autenticación excepto POST /api/auth/login
- Dependency injection para auth: `current_user = Depends(get_current_user)`
- Permisos como dependency: `Depends(require_role("admin"))`
- Audit logging automático via middleware (no manual en cada endpoint)
- Secrets NUNCA se logean en texto plano (ni en audit ni en errors)

### Frontend (React)
- Mismas convenciones del Proyecto 3
- JWT se almacena SOLO en memory (React state), NUNCA en localStorage
- Refresh token en httpOnly cookie (si se implementa) o re-login
- Componentes muestran/ocultan acciones basándose en permisos del usuario
- Toasts para feedback de acciones (éxito/error)

## Reglas de implementación

1. **Spec-first**: No implementes nada fuera de la spec.
2. **Auth antes que todo**: La autenticación debe funcionar antes de implementar cualquier endpoint protegido.
3. **Permisos en backend Y frontend**: El backend RECHAZA operaciones no autorizadas. El frontend OCULTA botones/acciones no disponibles. Ambos son necesarios.
4. **Secrets encriptados**: Los valores de tipo `secret` se encriptan en la DB con Fernet. Se desencriptan solo al leerlos (y solo si el usuario tiene permiso).
5. **Audit todo**: Cada operación que modifica datos genera un registro de auditoría.
6. **Redis es opcional para funcionar**: Si Redis no está disponible, el sistema debe funcionar sin cache (solo más lento). El cache es mejora, no requisito.

## Comandos del proyecto

```bash
# ── Iniciar Redis (via Docker) ──
docker-compose up -d redis

# ── Backend ──
cd backend
pip install -r requirements.txt
python seed.py                        # Crea usuario admin (admin/admin123)
uvicorn app.main:app --reload --port 8000
pytest tests/ -v

# ── Frontend ──
cd frontend
npm install
npm run dev

# ── Puertos ──
# Backend:  http://localhost:8000
# Frontend: http://localhost:5173
# Redis:    localhost:6379
```

## Variables de configuración (app/config.py)

```python
JWT_SECRET_KEY = "dev-secret-change-in-production"
JWT_ALGORITHM = "HS256"
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = 30
FERNET_KEY = "generated-on-first-run"   # Se genera automáticamente
REDIS_URL = "redis://localhost:6379"
DATABASE_URL = "sqlite+aiosqlite:///./config_vault.db"
```
