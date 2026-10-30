# Joyería Xavier — Sistema integrado de atención al cliente y gestión de órdenes

Proyecto Capstone (TITA7912) · Universidad de Las Américas · Ingeniería de Software.

Sistema para una joyería PYME de Quito que integra un agente conversacional con IA (WhatsApp, Instagram y Facebook vía Meta Business API), una plataforma web con catálogo y cotizador, y un módulo de gestión de órdenes de producción con panel administrativo.

**Autores:** Pablo David Yánez Alvear · Víctor Andrés Suquilanda Cartuche
**Tutor:** Martín Nicolas Almeida Gachet
**Gestión del proyecto:** Jira, espacio `JOY` (enlace: _por completar_)

## Estructura del repositorio

| Carpeta | Contenido |
|---|---|
| `01_documentacion/` | Documento del proyecto, diagramas C4 (niveles 1, 2 y 3), plan de pruebas |
| `02_codigo_fuente/` | Código del sistema (backend, frontend, agente, integración Meta, base de datos) |
| `03_pruebas/` | Pruebas unitarias, de integración y E2E, con su reporte |
| `04_despliegue_ci_cd/` | Docker Compose, configuración de Nginx y documentación del pipeline |
| `05_evidencias/` | Capturas de Jira (backlog, sprints, tablero), ejecuciones de CI/CD, resultados de pruebas |

Los workflows de GitHub Actions viven en `.github/workflows/` (requisito de GitHub) y se documentan en `04_despliegue_ci_cd/`.

## Stack

React + Vite · FastAPI (Python) · LangChain + LLM externo · PostgreSQL · Redis · Docker Compose · GitHub Actions · Contabo VPS.

## Instalación y ejecución

Requisitos: Git, Docker Desktop, Python 3.11 o superior y Node.js 20.19 o superior.

### 1. Clonar el repositorio

```
git clone https://github.com/pabloyanez5/joyeria-xavier.git
cd joyeria-xavier
```

### 2. Base de datos y caché (PostgreSQL y Redis)

```
cd 04_despliegue_ci_cd
docker compose up -d
docker compose ps
```

Ambos contenedores deben aparecer como `healthy`. Para apagarlos: `docker compose down`.
Los valores por defecto coinciden con `.env.example`, así que no necesitas crear un `.env` para desarrollo local.

### 3. Backend (FastAPI)

```
cd 02_codigo_fuente/backend
python -m venv .venv
.venv\Scripts\activate          # en Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head            # aplica las migraciones a PostgreSQL
pytest                          # ejecuta las pruebas
uvicorn app.main:app --reload
```

Comprobación: `http://127.0.0.1:8000/health` debe responder `{"status":"ok"}`. La documentación automática está en `http://127.0.0.1:8000/docs`.

### 4. Frontend (React + Vite)

```
cd 02_codigo_fuente/frontend/web
npm install
npm run dev
```

Abre `http://localhost:5173`.

### Nota para Windows con Control de aplicaciones

Si Windows bloquea binarios compilados (error "Una directiva de Control de aplicaciones bloqueó este archivo"), instala SQLAlchemy en Python puro:

```
set DISABLE_SQLALCHEMY_CEXT=1
pip install --no-binary sqlalchemy --no-cache-dir sqlalchemy
```

La conexión a PostgreSQL usa `pg8000` (Python puro) justamente para evitar ese bloqueo.

### Nueva migración

```
alembic revision --autogenerate -m "descripcion"
alembic upgrade head
```

## Variables y secretos

Las credenciales (Meta Business API, proveedor de LLM, base de datos, Redis, JWT) **nunca** se suben al repositorio. Usa `.env` en local (ignorado por git) y secretos de GitHub Actions para CI/CD. `.env.example` solo trae los nombres de las variables.

## Flujo de trabajo

- `main`: producción. Solo recibe merges desde `develop` con el pipeline en verde.
- `develop`: integración continua.
- `feature/JOY-<n>-descripcion`: una rama por actividad de Jira.
- Commits en español con la clave de Jira: `JOY-10: estructura inicial del repositorio`.
- Todo cambio entra por Pull Request.
