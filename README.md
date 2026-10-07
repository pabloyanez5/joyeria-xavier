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

_Se completa durante el Sprint 0 (US-00)._ Debe permitir levantar el sistema en local siguiendo estos pasos:

1. Clonar el repositorio.
2. Copiar `.env.example` a `.env` y completar los valores.
3. Levantar los servicios con Docker Compose.
4. Ejecutar las migraciones de base de datos.
5. Abrir la plataforma web y el panel administrativo.

## Variables y secretos

Las credenciales (Meta Business API, proveedor de LLM, base de datos, Redis, JWT) **nunca** se suben al repositorio. Usa `.env` en local (ignorado por git) y secretos de GitHub Actions para CI/CD. `.env.example` solo trae los nombres de las variables.

## Flujo de trabajo

- `main`: producción. Solo recibe merges desde `develop` con el pipeline en verde.
- `develop`: integración continua.
- `feature/JOY-<n>-descripcion`: una rama por actividad de Jira.
- Commits en español con la clave de Jira: `JOY-10: estructura inicial del repositorio`.
- Todo cambio entra por Pull Request.
