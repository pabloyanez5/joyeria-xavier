# Despliegue (staging) en el VPS

Entorno de pruebas en un VPS de Contabo (Ubuntu 24.04). Todo corre con Docker Compose:

| Servicio | Imagen | Notas |
|---|---|---|
| `web` | Nginx + build de React | Único puerto público (80). Sirve la web, reenvía `/api/` al backend y pide usuario y clave en `/panel`, `/api/ordenes` y `/api/clientes` |
| `api` | FastAPI (`02_codigo_fuente/backend/Dockerfile`) | Al arrancar aplica las migraciones (`alembic upgrade head`) |
| `db` | PostgreSQL 16 | Sin puerto público; datos en el volumen `pgdata` |
| `redis` | Redis 7 | Sin puerto público |

Archivos: `docker-compose.staging.yml`, `nginx/staging.conf`, `nginx/proxy.inc`, `staging.env.example`.
El flujo automático está en `.github/workflows/deploy-staging.yml`.

Para desarrollo local se sigue usando `docker-compose.yml` (solo base de datos y Redis). Staging tiene su propio nombre de proyecto (`joyeria-staging`) y su propio volumen, así que ambos pueden convivir en la misma máquina sin mezclarse.

## Preparación única del servidor

1. Usuario `deploy` con llave SSH y sin contraseña; acceso por contraseña y por `root` desactivados.
2. Firewall `ufw`: solo puertos 22, 80 y 443.
3. Docker y Docker Compose instalados; `deploy` pertenece al grupo `docker`.
4. Repositorio clonado en `~/joyeria-xavier` (rama `develop`).
5. Archivo `04_despliegue_ci_cd/.env` creado a partir de `staging.env.example` (no se sube al repositorio).
6. Archivo `04_despliegue_ci_cd/nginx/.htpasswd` con el usuario y la clave del panel (no se sube al repositorio):
   ```
   printf 'asesor:%s\n' "$(openssl passwd -apr1)" > nginx/.htpasswd
   ```

## Primer despliegue

```
cd ~/joyeria-xavier/04_despliegue_ci_cd
docker compose -f docker-compose.staging.yml up -d --build
docker compose -f docker-compose.staging.yml ps
docker compose -f docker-compose.staging.yml exec api python -m app.seed   # catálogo de prueba
```

Comprobación: `http://IP-DEL-SERVIDOR/api/health` debe responder `{"status":"ok"}`.

## Despliegue automático (GitHub Actions)

Cada cambio que entra a `develop` ejecuta `deploy-staging.yml`: se conecta por SSH al VPS, actualiza el código, reconstruye los contenedores, reinicia `web` y comprueba `/api/health`.
Secretos del repositorio (Settings → Secrets and variables → Actions):

| Secreto | Contenido |
|---|---|
| `STAGING_HOST` | IP del servidor |
| `STAGING_SSH_KEY` | Llave privada exclusiva del pipeline (usuario `deploy`) |
| `STAGING_KNOWN_HOSTS` | Huella del servidor (`ssh-keyscan -t ed25519 IP`) |

## Operación

```
docker compose -f docker-compose.staging.yml logs -f api      # registros del backend
docker compose -f docker-compose.staging.yml restart api
docker compose -f docker-compose.staging.yml down             # apaga (los datos se conservan)
```

## Limitaciones conocidas

- Solo HTTP (sin dominio): Meta exige HTTPS para su webhook, así que la conexión real con Meta queda para cuando haya dominio y certificado.
- Los datos son de prueba (ficticios).
- El servidor no tiene respaldos automáticos.
