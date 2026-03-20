# Proyecto 4: Config Vault — Guía SDD con Claude Code

## 🎯 Objetivo de aprendizaje

Aprender a escribir **especificaciones con lógica de negocio compleja**:
- Roles y permisos (quién puede hacer qué)
- Diagramas de estado para flujos de aprobación
- Especificar seguridad (autenticación, autorización, secrets)
- Auditoría (registrar cada acción con quién, qué, cuándo)
- Requisitos no funcionales en la spec (encriptación, cache, performance)

```
Spec de roles/permisos → Spec de datos → Spec de flujos → Spec de endpoints → Spec de UI
```

---

## 🔄 Qué cambió respecto al Proyecto 3

| Proyecto 3 (Pipeline Dashboard) | Proyecto 4 (Config Vault) |
|---------------------------------|---------------------------|
| Sin autenticación | JWT + roles + permisos |
| Cualquiera ve todo | Acceso según rol y proyecto |
| Operaciones simples (CRUD) | Flujos de aprobación con estados |
| Datos públicos | Secrets encriptados |
| Sin auditoría | Cada acción queda registrada |
| 4 specs | 5 specs (nueva: auth-and-roles) |

---

## 📁 Los archivos de spec (léelos EN ESTE ORDEN)

1. **CLAUDE.md** → Reglas globales
2. **specs/auth-and-roles.spec.md** → ⭐ NUEVO: Autenticación, roles, permisos (LEER PRIMERO)
3. **specs/shared-contracts.spec.md** → Modelos de datos compartidos
4. **specs/backend-api.spec.md** → Endpoints REST
5. **specs/frontend-ui.spec.md** → Componentes React
6. **PROMPTS-CLAUDE-CODE.md** → Prompts para Claude Code

---

## 🏗️ Arquitectura del sistema

```
┌──────────────────────────────────────────────────┐
│                   Frontend                        │
│                (React + Vite)                     │
│                                                   │
│  ┌────────┐ ┌──────────┐ ┌──────┐ ┌───────────┐ │
│  │ Login  │ │ Projects │ │Config│ │ Approvals │ │
│  │        │ │ & Envs   │ │Editor│ │ & Audit   │ │
│  └────────┘ └──────────┘ └──────┘ └───────────┘ │
│         │          │          │          │        │
│    JWT Token almacenado en memoria (state)        │
│         └──────────┼──────────┘          │        │
│                    │ REST + Bearer Token  │        │
└────────────────────┼─────────────────────┘────────┘
                     │
┌────────────────────┼──────────────────────────────┐
│                    │           Backend             │
│              (FastAPI + SQLite)                    │
│                                                    │
│  ┌──────────┐ ┌──────────┐ ┌─────────┐           │
│  │ Auth     │ │ Config   │ │ Approval│           │
│  │ (JWT)    │ │ CRUD     │ │ Flow    │           │
│  └──────────┘ └──────────┘ └─────────┘           │
│       │             │            │                 │
│  ┌────▼─────────────▼────────────▼──────────────┐ │
│  │           Audit Logger (middleware)           │ │
│  └──────────────────┬───────────────────────────┘ │
│                     │                              │
│  ┌──────────┐  ┌────▼─────┐                       │
│  │  Redis   │  │  SQLite  │                       │
│  │ (cache)  │  │  (data)  │                       │
│  └──────────┘  └──────────┘                       │
└────────────────────────────────────────────────────┘
```

---

## 🏁 Fases del proyecto

| Fase | Qué implementas | Qué aprendes de SDD |
|------|-----------------|---------------------|
| 1 | Modelos + DB + Auth (JWT + roles) | Specs de autenticación y autorización |
| 2 | CRUD de Projects + Environments + Configs | Specs con permisos por operación |
| 3 | Feature Flags + Secrets encriptados | Specs de seguridad y tipos especiales |
| 4 | Flujo de aprobación para producción | Specs de máquinas de estado |
| 5 | Audit log + Redis cache | Specs de requisitos no funcionales |
| 6 | Frontend: Auth + Config Editor + Approvals | Specs de UI con contexto de permisos |
| 7 | Tests E2E + integración completa | Specs de escenarios multi-rol |

---

## 💡 La lección clave de este proyecto

**La spec de roles y permisos es el contrato más crítico del sistema.**

Cada endpoint, cada botón en la UI, cada operación depende de la pregunta
"¿este usuario tiene permiso para hacer esto?". Si esa spec no es cristalina,
la implementación será un laberinto de `if/else`.

La spec `auth-and-roles.spec.md` define una **matriz de permisos**: para cada
combinación de rol × recurso × acción, dice explícitamente si está permitido
o no. Esa matriz es la que los tests deben verificar exhaustivamente.

---

## ⚠️ Sesiones de Claude Code recomendadas

1. **Sesión Backend Auth** (Fase 1): Auth es fundamental, debe funcionar sola
2. **Sesión Backend Core** (Fases 2-5): CRUD + aprobaciones + audit
3. **Sesión Frontend** (Fase 6): UI completa con contexto de auth
4. **Sesión Integración** (Fase 7): Tests multi-rol end-to-end
