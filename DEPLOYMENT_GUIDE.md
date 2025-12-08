# Guía de Deployment - GrupoDC Agent Service

## 📋 Resumen

Esta guía explica cómo hacer deployment completo del servicio con:
- ✅ **Azure Bot Framework** (Legacy - Teams Bot)
- ✅ **Teams Tabs SSO** (JWT token authentication)
- ✅ **Web OAuth2** (Microsoft login para aplicaciones web)
- ✅ **Cloud SQL PostgreSQL** (sesiones persistentes)
- ✅ **Vertex AI** con Gemini 2.5 Flash

---

## 🚀 Deployment Rápido

### Paso 1: Configurar Variables

Edita `deploy-config.sh` y actualiza:

```bash
# GCP
export PROJECT_ID="your-project-id"              # ⚠️ REQUERIDO
export REGION="us-east4"
export SERVICE_NAME="grupodc-agent-backend-dev"

# Azure AD
export AZURE_TENANT_ID="your-tenant-id"          # ⚠️ REQUERIDO
export AZURE_CLIENT_ID="8f932a37-..."            # ⚠️ REQUERIDO
export AZURE_CLIENT_SECRET="your-secret"         # ⚠️ REQUERIDO
```

### Paso 2: Ejecutar Deployment

```bash
./deploy-complete.sh
```

El script automáticamente:
1. Habilita APIs de GCP necesarias
2. Configura IAM permissions
3. Crea instancia de Cloud SQL PostgreSQL
4. Inicializa schema de base de datos
5. Guarda secretos en Secret Manager
6. Construye imagen Docker
7. Despliega a Cloud Run
8. Verifica el deployment

**Tiempo estimado**: 10-15 minutos

---

## 📝 Pre-requisitos

### 1. GCP Project Setup

```bash
# Instalar gcloud CLI
# https://cloud.google.com/sdk/docs/install

# Autenticarse
gcloud auth login

# Configurar proyecto
gcloud config set project YOUR_PROJECT_ID
```

### 2. Azure AD App Registration

**Crear App Registration**:
1. Ir a: https://portal.azure.com
2. Azure Active Directory → App registrations
3. Click "New registration"
4. Nombre: "GrupoDC Agent Backend"
5. Supported account types: Single tenant (o según necesites)
6. Click "Register"

**Configurar Authentication**:
1. Go to **Authentication**
2. Add platform → Web
3. Add Redirect URI:
   ```
   https://grupodc-agent-backend-dev-118078450167.us-east4.run.app/api/v1/auth/callback
   http://localhost:8080/api/v1/auth/callback  (para desarrollo)
   ```
4. Implicit grant → ☑️ ID tokens (para Teams Tab)

**Configurar API Permissions**:
1. Go to **API permissions**
2. Add permission → Microsoft Graph → Delegated permissions
3. Agregar:
   - `openid`
   - `profile`
   - `email`
   - `User.Read`
4. Click "Grant admin consent"

**Obtener Credentials**:
1. Go to **Overview** → copiar:
   - **Application (client) ID** → Usar como `AZURE_CLIENT_ID`
   - **Directory (tenant) ID** → Usar como `AZURE_TENANT_ID`

2. Go to **Certificates & secrets** → New client secret
   - Description: "Backend OAuth2"
   - Expires: 24 months
   - Click "Add"
   - **Copiar el valor INMEDIATAMENTE** → Usar como `AZURE_CLIENT_SECRET`

### 3. Herramientas Necesarias

```bash
# PostgreSQL client (para migrations)
# Ubuntu/Debian:
sudo apt-get install postgresql-client

# macOS:
brew install postgresql

# OpenSSL (para generar passwords)
# Ya viene instalado en Linux/macOS
```

---

## 🔧 Configuración Detallada

### Variables de Entorno en Cloud Run

El script configura automáticamente estas variables:

```bash
# Aplicación
ENVIRONMENT=production
PERSIST_SESSIONS=true                    # ✅ Siempre habilitado

# Google Cloud
GOOGLE_CLOUD_PROJECT=<auto>              # Auto-configurado
GOOGLE_GENAI_USE_VERTEXAI=TRUE

# Base de Datos
DB_HOST=/cloudsql/<connection-name>
DB_PORT=5432
DB_NAME=agents_db
DB_USER=agents_app
DB_PASSWORD=<from-secret-manager>

# Azure AD
AZURE_TENANT_ID=<your-tenant>
AZURE_CLIENT_ID=<your-client-id>
AZURE_CLIENT_SECRET=<from-secret-manager>
AZURE_REDIRECT_URI=https://your-url.run.app/api/v1/auth/callback
FRONTEND_URL=https://your-frontend.com

# Microsoft Graph (opcional)
GRAPH_TENANT_ID=<same-as-azure>
GRAPH_CLIENT_ID=<same-as-azure>
GRAPH_CLIENT_SECRET=<from-secret-manager>
```

### Secretos en Secret Manager

El script crea estos secretos automáticamente:

1. **`db-password`**: Contraseña de PostgreSQL
2. **`azure-client-secret`**: Client secret de Azure AD
3. **`graph-client-secret`**: Client secret de Graph API (si es diferente)

**Ver secretos**:
```bash
# Listar secretos
gcloud secrets list

# Ver valor de un secreto
gcloud secrets versions access latest --secret=db-password
```

---

## 🗄️ Base de Datos

### Configuración Automática

El script crea:
- Instancia Cloud SQL PostgreSQL 16
- Usuario `postgres` (root)
- Base de datos `agents_db`
- Usuario de aplicación `agents_app`
- Todas las tablas necesarias (desde schema.sql)

### Conexión Manual

```bash
# Descargar Cloud SQL Proxy
curl -o cloud-sql-proxy https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/v2.8.0/cloud-sql-proxy.linux.amd64
chmod +x cloud-sql-proxy

# Conectar
./cloud-sql-proxy PROJECT:REGION:INSTANCE &

# Conectar con psql
psql -h 127.0.0.1 -U agents_app -d agents_db
```

### Migraciones

El script ejecuta automáticamente:
1. `src/infrastructure/adapters/postgres/schema.sql` - Schema inicial
2. `migrations/002_remove_area_type_constraint.sql` - Migración 002
3. `migrations/003_azure_ad_group_mappings.sql` - Migración 003

**Ejecutar nueva migración manualmente**:
```bash
PGPASSWORD="your-password" psql -h 127.0.0.1 -U agents_app -d agents_db \
  -f migrations/004_your_migration.sql
```

---

## 🧪 Testing del Deployment

### 1. Health Check

```bash
export SERVICE_URL="https://grupodc-agent-backend-dev-118078450167.us-east4.run.app"

curl -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  $SERVICE_URL/health
```

**Respuesta esperada**:
```json
{
  "status": "healthy",
  "version": "2.0.0",
  "mode": "multi (bot + tabs + web)",
  "authentication": {
    "teams_bot": true,
    "teams_sso": true,
    "web_oauth2": true
  },
  "endpoints": {
    "auth_login": "/api/v1/auth/login-url",
    "auth_callback": "/api/v1/auth/callback",
    "auth_me": "/api/v1/auth/me"
  }
}
```

### 2. Test OAuth2 Login Flow

```bash
# Obtener URL de login
curl -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  "$SERVICE_URL/api/v1/auth/login-url?redirect_uri=https://grupodc-agent-backend-dev-118078450167.us-east4.run.app/api/v1/auth/callback"
```

**Respuesta**:
```json
{
  "login_url": "https://login.microsoftonline.com/...",
  "state": "random-csrf-token"
}
```

Abre el `login_url` en un navegador → login con Microsoft → serás redirigido al frontend con una session cookie.

### 3. Test Auth Status

```bash
curl -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  $SERVICE_URL/api/v1/auth/status
```

**Sin autenticación**:
```json
{
  "authenticated": false,
  "user": null
}
```

### 4. Test Teams Bot (Legacy)

```bash
curl -X POST \
  -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  -H "Content-Type: application/json" \
  -d '{
    "user_message": "Hello from bot",
    "aad_user_id": "test-user-123",
    "user_name": "Test User"
  }' \
  $SERVICE_URL/api/v1/teams/message
```

### 5. Test Teams Tab / Web Invoke

**Con Teams SSO token**:
```bash
curl -X POST \
  -H "Authorization: Bearer YOUR_TEAMS_SSO_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "What is the weather?",
    "agent_name": "search_assistant"
  }' \
  $SERVICE_URL/api/v1/tabs/invoke
```

**Con session cookie (después de OAuth2 login)**:
```bash
curl -X POST \
  -H "Cookie: session_id=YOUR_SESSION_ID" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "What is the weather?",
    "agent_name": "search_assistant"
  }' \
  $SERVICE_URL/api/v1/tabs/invoke
```

---

## 📊 Monitoreo y Logs

### Ver Logs en Tiempo Real

```bash
gcloud logging tail \
  "resource.type=cloud_run_revision AND resource.labels.service_name=grupodc-agent-backend-dev" \
  --project=your-project-id
```

### Ver Logs en Cloud Console

```
https://console.cloud.google.com/run/detail/us-east4/grupodc-agent-backend-dev/logs
```

### Filtrar Logs por Severidad

```bash
# Solo errores
gcloud logging read \
  "resource.type=cloud_run_revision AND severity=ERROR" \
  --limit=50 \
  --format=json

# Authentication logs
gcloud logging read \
  "resource.type=cloud_run_revision AND textPayload=~'Authenticated'" \
  --limit=50
```

### Métricas en Cloud Console

```
https://console.cloud.google.com/run/detail/us-east4/grupodc-agent-backend-dev/metrics
```

Métricas importantes:
- Request count
- Request latency (P50, P95, P99)
- Error rate
- Container CPU/Memory usage
- Cold starts

---

## 🔄 Actualizar el Servicio

### Actualizar Código

```bash
# 1. Hacer cambios en el código
# 2. Commit y push

# 3. Rebuild y redeploy
gcloud builds submit --tag gcr.io/your-project/grupodc-agent-backend-dev

gcloud run deploy grupodc-agent-backend-dev \
  --image gcr.io/your-project/grupodc-agent-backend-dev \
  --region=us-east4
```

### Actualizar Variables de Entorno

```bash
# Actualizar una variable
gcloud run services update grupodc-agent-backend-dev \
  --region=us-east4 \
  --update-env-vars="FRONTEND_URL=https://new-frontend.com"

# Actualizar múltiples variables
gcloud run services update grupodc-agent-backend-dev \
  --region=us-east4 \
  --update-env-vars="FRONTEND_URL=https://new-frontend.com,LOG_LEVEL=DEBUG"
```

### Actualizar Secretos

```bash
# Crear nueva versión del secreto
echo -n "new-secret-value" | gcloud secrets versions add azure-client-secret --data-file=-

# Cloud Run automáticamente usará la nueva versión en el próximo deploy
```

### Rollback a Versión Anterior

```bash
# Listar revisiones
gcloud run revisions list \
  --service=grupodc-agent-backend-dev \
  --region=us-east4

# Rollback a revisión específica
gcloud run services update-traffic grupodc-agent-backend-dev \
  --region=us-east4 \
  --to-revisions=grupodc-agent-backend-dev-00001-abc=100
```

---

## 🔒 Seguridad

### Secrets Management

**❌ NUNCA hacer**:
- Commitear secrets al repositorio
- Logear valores de secrets
- Compartir secrets por Slack/email
- Usar secrets en URLs

**✅ SIEMPRE hacer**:
- Usar Secret Manager para secrets
- Rotar secrets regularmente (cada 3-6 meses)
- Usar diferentes secrets para dev/staging/prod
- Limitar acceso a secrets con IAM

### IAM Permissions

**Principio de mínimo privilegio**:
```bash
# Cloud Run service account solo necesita:
- roles/cloudsql.client (para Cloud SQL)
- roles/secretmanager.secretAccessor (para secrets)
- roles/aiplatform.user (para Vertex AI)

# No dar roles/editor o roles/owner
```

### CORS Configuration

Actualizar `src/main.py` línea 78 con tu frontend:

```python
allow_origins=[
    "https://teams.microsoft.com",
    "https://*.teams.microsoft.com",
    "https://your-frontend-domain.com",  # ⚠️ AGREGAR AQUÍ
    # Quitar "*" en producción
]
```

---

## 🐛 Troubleshooting

### Error: "AZURE_TENANT_ID or AZURE_CLIENT_ID not set"

**Solución**:
```bash
# Verificar variables en Cloud Run
gcloud run services describe grupodc-agent-backend-dev \
  --region=us-east4 \
  --format="value(spec.template.spec.containers[0].env)"

# Actualizar si faltan
gcloud run services update grupodc-agent-backend-dev \
  --region=us-east4 \
  --update-env-vars="AZURE_TENANT_ID=xxx,AZURE_CLIENT_ID=xxx"
```

### Error: "Invalid token audience"

**Causa**: El `AZURE_CLIENT_ID` no coincide con el token.

**Solución**: Verificar que `AZURE_CLIENT_ID` en Cloud Run es el mismo que en Azure AD App Registration.

### Error: "Redirect URI mismatch"

**Causa**: El redirect URI no está configurado en Azure AD.

**Solución**:
1. Ir a Azure Portal → Azure AD → App Registrations → Tu App
2. Authentication → Add Web redirect URI:
   ```
   https://grupodc-agent-backend-dev-118078450167.us-east4.run.app/api/v1/auth/callback
   ```

### Error: "CORS error" desde frontend

**Solución**: Agregar dominio del frontend a `allow_origins` en `src/main.py:78`.

### Error: Database connection failed

**Verificar**:
```bash
# 1. Instancia está running
gcloud sql instances describe adk-agents-db

# 2. Cloud Run tiene conexión configurada
gcloud run services describe grupodc-agent-backend-dev \
  --region=us-east4 \
  --format="value(spec.template.metadata.annotations)"

# 3. Service account tiene permiso
gcloud projects get-iam-policy your-project \
  --flatten="bindings[].members" \
  --filter="bindings.members:*compute@developer.gserviceaccount.com"
```

### Service No Responde

```bash
# Ver logs en tiempo real
gcloud logging tail \
  "resource.type=cloud_run_revision AND resource.labels.service_name=grupodc-agent-backend-dev"

# Ver últimas 50 líneas
gcloud logging read \
  "resource.type=cloud_run_revision AND resource.labels.service_name=grupodc-agent-backend-dev" \
  --limit=50
```

---

## 💰 Costos Estimados

### Configuración Actual

- **Cloud Run**:
  - Memoria: 1 GiB
  - CPU: 1
  - Min instances: 0 (scale to zero)
  - Max instances: 10
  - **Costo**: ~$0-50/mes (depende de tráfico)

- **Cloud SQL**:
  - Tier: db-custom-1-3840 (1 vCPU, 3.75GB RAM)
  - Storage: 10GB (auto-increase)
  - Backups: Diarios
  - **Costo**: ~$50-70/mes

- **Secret Manager**:
  - 3 secretos activos
  - **Costo**: ~$0.36/mes

- **Vertex AI**:
  - Gemini 2.5 Flash
  - **Costo**: Por uso (input/output tokens)

**Total estimado**: ~$50-120/mes (dependiendo de uso)

### Optimizar Costos

**Reducir costos de Cloud SQL**:
```bash
# Usar tier más pequeño
--tier=db-f1-micro  # ~$7/mes (solo desarrollo)

# Pausar instancia cuando no se usa
gcloud sql instances patch adk-agents-db --activation-policy=NEVER
```

**Reducir costos de Cloud Run**:
```bash
# Reducir memoria
--memory=512Mi  # En vez de 1Gi

# Mantener min-instances=0 para scale to zero
```

---

## 📞 Soporte

### Logs de Deployment

Después del deployment, los credentials se guardan en:
```
~/.gcp-secrets/db-passwords-YOUR_PROJECT_ID.txt
```

**⚠️ IMPORTANTE**: Este archivo contiene información sensible. Guardarlo en un password manager seguro.

### Comandos Útiles

```bash
# Ver service URL
gcloud run services describe grupodc-agent-backend-dev \
  --region=us-east4 \
  --format="value(status.url)"

# Ver todas las env vars
gcloud run services describe grupodc-agent-backend-dev \
  --region=us-east4 \
  --format="yaml(spec.template.spec.containers[0].env)"

# Ver Cloud SQL connection
gcloud sql instances describe adk-agents-db \
  --format="value(connectionName)"

# Acceso a base de datos
gcloud sql connect adk-agents-db --user=agents_app --database=agents_db
```

### Documentación Adicional

- **Variables de Entorno**: Ver `ENVIRONMENT_VARIABLES.md`
- **Azure AD Setup**: Ver `AZURE_AD_SETUP_AND_TESTING.md`
- **Frontend Requirements**: Ver `FRONTEND_INFRASTRUCTURE_REQUIREMENTS.md`
- **Migración Teams Tabs**: Ver `MIGRATION_TEAMS_TABS.md`

---

## ✅ Checklist de Deployment

- [ ] GCP project configurado
- [ ] Azure AD App Registration creada
- [ ] Client secret obtenido de Azure AD
- [ ] `deploy-config.sh` actualizado con tus valores
- [ ] PostgreSQL client instalado
- [ ] Ejecutar `./deploy-complete.sh`
- [ ] Verificar health check pasa
- [ ] Agregar redirect URI en Azure AD
- [ ] Conceder API permissions en Azure AD
- [ ] Grant admin consent
- [ ] Probar OAuth2 login flow
- [ ] Actualizar CORS con frontend domain
- [ ] Deploy frontend
- [ ] Actualizar `FRONTEND_URL` en Cloud Run
- [ ] Probar integración completa

---

**¡Listo para producción!** 🎉
