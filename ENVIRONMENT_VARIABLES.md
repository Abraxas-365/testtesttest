# Variables de Entorno del Proyecto

## 📋 Resumen de Todas las Variables

Este documento lista **todas** las variables de entorno utilizadas en el proyecto, organizadas por categoría.

---

## 🔧 1. CONFIGURACIÓN DE LA APLICACIÓN

### `PORT`
- **Tipo**: Integer
- **Default**: `8080`
- **Requerido**: No
- **Descripción**: Puerto en el que se ejecuta el servidor FastAPI
- **Ejemplo**: `PORT=8080`

### `HOST`
- **Tipo**: String
- **Default**: `0.0.0.0`
- **Requerido**: No
- **Descripción**: Host/IP en la que escucha el servidor
- **Ejemplo**: `HOST=0.0.0.0`

### `ENVIRONMENT`
- **Tipo**: String (enum)
- **Default**: `production`
- **Valores**: `development`, `staging`, `production`
- **Requerido**: No
- **Descripción**: Entorno de ejecución. Cuando es `development`, habilita auto-reload
- **Ejemplo**: `ENVIRONMENT=development`

### `LOG_LEVEL`
- **Tipo**: String (enum)
- **Default**: `INFO`
- **Valores**: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`
- **Requerido**: No
- **Descripción**: Nivel de logging de la aplicación
- **Ejemplo**: `LOG_LEVEL=INFO`

---

## 💾 2. BASE DE DATOS (PostgreSQL)

### `DB_HOST`
- **Tipo**: String
- **Default**: `localhost`
- **Requerido**: Sí (si usas PostgreSQL)
- **Descripción**: Hostname del servidor PostgreSQL
- **Ejemplo**: `DB_HOST=localhost`
- **Cloud Run**: `DB_HOST=10.1.2.3` (Cloud SQL Private IP)

### `DB_PORT`
- **Tipo**: Integer
- **Default**: `5432`
- **Requerido**: No
- **Descripción**: Puerto del servidor PostgreSQL
- **Ejemplo**: `DB_PORT=5432`

### `DB_NAME`
- **Tipo**: String
- **Default**: `agents_db`
- **Requerido**: Sí (si usas PostgreSQL)
- **Descripción**: Nombre de la base de datos
- **Ejemplo**: `DB_NAME=agents_db`

### `DB_USER`
- **Tipo**: String
- **Default**: `postgres`
- **Requerido**: Sí (si usas PostgreSQL)
- **Descripción**: Usuario de PostgreSQL
- **Ejemplo**: `DB_USER=postgres`

### `DB_PASSWORD`
- **Tipo**: String (SECRET)
- **Default**: `postgres`
- **Requerido**: Sí (si usas PostgreSQL)
- **Descripción**: Contraseña del usuario de PostgreSQL
- **Ejemplo**: `DB_PASSWORD=super-secret-password`
- **⚠️ NUNCA COMMITEAR AL REPOSITORIO**

### `PERSIST_SESSIONS`
- **Tipo**: Boolean
- **Default**: `false`
- **Valores**: `true`, `false`
- **Requerido**: No
- **Descripción**: Habilita sesiones persistentes en base de datos (usando ADK DatabaseSessionService)
- **Ejemplo**: `PERSIST_SESSIONS=true`
- **Nota**: Requiere PostgreSQL configurado

---

## ☁️ 3. GOOGLE CLOUD PLATFORM (GCP)

### `GOOGLE_CLOUD_PROJECT`
- **Tipo**: String
- **Default**: None
- **Requerido**: Sí
- **Descripción**: ID del proyecto de GCP
- **Ejemplo**: `GOOGLE_CLOUD_PROJECT=my-project-12345`
- **Cloud Run**: Auto-configurado por Cloud Run

### `GOOGLE_CLOUD_LOCATION`
- **Tipo**: String
- **Default**: `us-east4`
- **Requerido**: Sí (para Vertex AI)
- **Descripción**: Región de GCP para Vertex AI
- **Ejemplo**: `GOOGLE_CLOUD_LOCATION=us-east4`
- **Opciones comunes**: `us-central1`, `us-east4`, `europe-west1`, `asia-northeast1`
- **Cloud Run**: Auto-configurado por Cloud Run

### `GOOGLE_APPLICATION_CREDENTIALS`
- **Tipo**: String (path)
- **Default**: None
- **Requerido**: No (solo desarrollo local)
- **Descripción**: Ruta al archivo JSON de credenciales de service account
- **Ejemplo**: `GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account-key.json`
- **Cloud Run**: No necesario (usa metadata server)

### `GOOGLE_GENAI_USE_VERTEXAI`
- **Tipo**: String
- **Default**: `TRUE`
- **Valores**: `TRUE`, `FALSE`
- **Requerido**: Sí
- **Descripción**: Indica al SDK de Google GenAI que use Vertex AI en lugar de Google AI API
- **Ejemplo**: `GOOGLE_GENAI_USE_VERTEXAI=TRUE`
- **Nota**: DEBE estar en `TRUE` para producción

### `GOOGLE_API_KEY`
- **Tipo**: String (SECRET)
- **Default**: None
- **Requerido**: No (cuando se usa Vertex AI)
- **Descripción**: API Key de Google AI (no necesario con Vertex AI)
- **Ejemplo**: `GOOGLE_API_KEY=AIzaSy...`
- **Nota**: NO usar en producción, usar Vertex AI

---

## 🔐 4. MICROSOFT AZURE AD / ENTRA ID

### `AZURE_TENANT_ID`
- **Tipo**: String (GUID)
- **Default**: None
- **Requerido**: Sí
- **Descripción**: ID del tenant de Azure AD (también llamado Directory ID)
- **Ejemplo**: `AZURE_TENANT_ID=12345678-1234-1234-1234-123456789012`
- **Donde obtener**: Azure Portal → Azure AD → Overview → Tenant ID

### `AZURE_CLIENT_ID`
- **Tipo**: String (GUID)
- **Default**: None
- **Requerido**: Sí
- **Descripción**: Application (client) ID de tu App Registration en Azure AD
- **Ejemplo**: `AZURE_CLIENT_ID=8f932a37-a7f6-4fe8-be5e-a72ab69758cf`
- **Donde obtener**: Azure Portal → Azure AD → App Registrations → Tu App → Application ID

### `AZURE_CLIENT_SECRET`
- **Tipo**: String (SECRET)
- **Default**: None
- **Requerido**: Sí
- **Descripción**: Client secret de tu App Registration en Azure AD
- **Ejemplo**: `AZURE_CLIENT_SECRET=AbC~123456789...`
- **Donde obtener**: Azure Portal → Azure AD → App Registrations → Tu App → Certificates & secrets
- **⚠️ NUNCA COMMITEAR AL REPOSITORIO**
- **⚠️ EXPIRA**: Crear nuevo secret cada 24 meses

### `AZURE_REDIRECT_URI`
- **Tipo**: String (URL)
- **Default**: None
- **Requerido**: Sí (para OAuth2 web)
- **Descripción**: URL de callback para OAuth2 (donde Microsoft redirige después del login)
- **Ejemplo Local**: `AZURE_REDIRECT_URI=http://localhost:8080/api/v1/auth/callback`
- **Ejemplo Prod**: `AZURE_REDIRECT_URI=https://grupodc-agent-backend-dev-118078450167.us-east4.run.app/api/v1/auth/callback`
- **⚠️ IMPORTANTE**: Debe coincidir EXACTAMENTE con lo configurado en Azure AD

### `FRONTEND_URL`
- **Tipo**: String (URL)
- **Default**: `http://localhost:5173`
- **Requerido**: Sí
- **Descripción**: URL del frontend para redirecciones post-login
- **Ejemplo Local**: `FRONTEND_URL=http://localhost:5173`
- **Ejemplo Prod**: `FRONTEND_URL=https://app.your-domain.com`

---

## 📊 5. MICROSOFT GRAPH API (Opcional)

### `GRAPH_TENANT_ID`
- **Tipo**: String (GUID)
- **Default**: None (usa `AZURE_TENANT_ID` si no está definido)
- **Requerido**: No
- **Descripción**: Tenant ID para Microsoft Graph API
- **Ejemplo**: `GRAPH_TENANT_ID=12345678-1234-1234-1234-123456789012`
- **Nota**: Normalmente debe ser igual a `AZURE_TENANT_ID`

### `GRAPH_CLIENT_ID`
- **Tipo**: String (GUID)
- **Default**: None (usa `AZURE_CLIENT_ID` si no está definido)
- **Requerido**: No
- **Descripción**: Client ID para Microsoft Graph API
- **Ejemplo**: `GRAPH_CLIENT_ID=8f932a37-a7f6-4fe8-be5e-a72ab69758cf`
- **Nota**: Normalmente debe ser igual a `AZURE_CLIENT_ID`

### `GRAPH_CLIENT_SECRET`
- **Tipo**: String (SECRET)
- **Default**: None (usa `AZURE_CLIENT_SECRET` si no está definido)
- **Requerido**: No
- **Descripción**: Client secret para Microsoft Graph API
- **Ejemplo**: `GRAPH_CLIENT_SECRET=AbC~123456789...`
- **Nota**: Normalmente debe ser igual a `AZURE_CLIENT_SECRET`
- **⚠️ NUNCA COMMITEAR AL REPOSITORIO**

---

## 📝 Resumen: Variables por Entorno

### Desarrollo Local (Mínimo Requerido)

```bash
# Aplicación
PORT=8080
ENVIRONMENT=development

# GCP (si tienes service account local)
GOOGLE_CLOUD_PROJECT=my-project-id
GOOGLE_CLOUD_LOCATION=us-east4
GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account-key.json
GOOGLE_GENAI_USE_VERTEXAI=TRUE

# Azure AD
AZURE_TENANT_ID=your-tenant-id
AZURE_CLIENT_ID=8f932a37-a7f6-4fe8-be5e-a72ab69758cf
AZURE_CLIENT_SECRET=your-secret
AZURE_REDIRECT_URI=http://localhost:8080/api/v1/auth/callback
FRONTEND_URL=http://localhost:5173

# Base de datos (opcional)
DB_HOST=localhost
DB_PORT=5432
DB_NAME=agents_db
DB_USER=postgres
DB_PASSWORD=postgres
```

### Cloud Run (Producción - Requerido)

```bash
# Estas se auto-configuran en Cloud Run:
# - GOOGLE_CLOUD_PROJECT
# - GOOGLE_CLOUD_LOCATION

# DEBES configurar manualmente:
GOOGLE_GENAI_USE_VERTEXAI=TRUE
AZURE_TENANT_ID=your-tenant-id
AZURE_CLIENT_ID=8f932a37-a7f6-4fe8-be5e-a72ab69758cf
AZURE_CLIENT_SECRET=your-secret
AZURE_REDIRECT_URI=https://grupodc-agent-backend-dev-118078450167.us-east4.run.app/api/v1/auth/callback
FRONTEND_URL=https://app.your-domain.com

# Opcionales:
ENVIRONMENT=production
LOG_LEVEL=INFO
DB_HOST=10.x.x.x  # Si usas Cloud SQL
DB_USER=postgres
DB_PASSWORD=your-db-password
PERSIST_SESSIONS=true
```

---

## 🔒 Seguridad: Variables Sensibles

**NUNCA commitear al repositorio**:
- ❌ `AZURE_CLIENT_SECRET`
- ❌ `DB_PASSWORD`
- ❌ `GOOGLE_API_KEY`
- ❌ `GRAPH_CLIENT_SECRET`
- ❌ `GOOGLE_APPLICATION_CREDENTIALS` (el archivo .json)

**Buenas prácticas**:
1. Usar Secret Manager de GCP para producción
2. Rotar secrets regularmente
3. Usar diferentes credentials para dev/staging/prod
4. Nunca logear valores de secrets

---

## 📋 Checklist de Configuración

### Para Desarrollo Local
- [ ] Copiar `.env.example` a `.env`
- [ ] Actualizar `AZURE_TENANT_ID`
- [ ] Actualizar `AZURE_CLIENT_ID`
- [ ] Actualizar `AZURE_CLIENT_SECRET`
- [ ] Actualizar `GOOGLE_CLOUD_PROJECT`
- [ ] Configurar `GOOGLE_APPLICATION_CREDENTIALS` (path al .json)
- [ ] Verificar que `.env` está en `.gitignore`

### Para Cloud Run
- [ ] Configurar `AZURE_TENANT_ID`
- [ ] Configurar `AZURE_CLIENT_ID`
- [ ] Configurar `AZURE_CLIENT_SECRET`
- [ ] Configurar `AZURE_REDIRECT_URI` (con URL de producción)
- [ ] Configurar `FRONTEND_URL` (con URL de producción)
- [ ] Agregar redirect URI en Azure AD App Registration
- [ ] Verificar `GOOGLE_GENAI_USE_VERTEXAI=TRUE`

---

## 🚀 Comandos Útiles

### Ver variables en Cloud Run
```bash
gcloud run services describe grupodc-agent-backend-dev \
  --region=us-east4 \
  --format="value(spec.template.spec.containers[0].env)"
```

### Actualizar variables en Cloud Run
```bash
gcloud run services update grupodc-agent-backend-dev \
  --region=us-east4 \
  --update-env-vars="AZURE_TENANT_ID=xxx,AZURE_CLIENT_ID=xxx,AZURE_CLIENT_SECRET=xxx,AZURE_REDIRECT_URI=https://your-url.com/api/v1/auth/callback,FRONTEND_URL=https://your-frontend.com"
```

### Eliminar una variable en Cloud Run
```bash
gcloud run services update grupodc-agent-backend-dev \
  --region=us-east4 \
  --remove-env-vars="VARIABLE_NAME"
```

---

## ❓ Preguntas Frecuentes

**Q: ¿Por qué hay AZURE_* y GRAPH_* variables?**
A: Para permitir flexibilidad. Si usas diferentes App Registrations para autenticación y Graph API, puedes configurarlas por separado. En la mayoría de casos, usa solo AZURE_*.

**Q: ¿Necesito GOOGLE_APPLICATION_CREDENTIALS en Cloud Run?**
A: No. Cloud Run usa automáticamente la service account asignada al servicio.

**Q: ¿Cuál es la diferencia entre GOOGLE_CLOUD_REGION y GOOGLE_CLOUD_LOCATION?**
A: Son lo mismo. El proyecto usa `GOOGLE_CLOUD_LOCATION` como estándar (nombre oficial de Vertex AI).

**Q: ¿Cómo obtengo mi AZURE_TENANT_ID?**
A: Azure Portal → Azure Active Directory → Overview → Tenant ID (GUID)

**Q: ¿Dónde configuro el AZURE_REDIRECT_URI en Azure?**
A: Azure Portal → Azure AD → App Registrations → Tu App → Authentication → Web Redirect URIs

**Q: ¿Qué pasa si no configuro PERSIST_SESSIONS?**
A: Las conversaciones se mantienen solo durante la request (in-memory). No hay persistencia entre requests.

---

## 📞 Soporte

Si tienes problemas con las variables de entorno:
1. Verifica que `.env` existe localmente
2. Verifica que las variables están configuradas en Cloud Run
3. Revisa los logs: `gcloud run logs read --service=grupodc-agent-backend-dev`
4. Usa el endpoint `/health` para verificar configuración

**Endpoint de diagnóstico**:
```bash
curl https://grupodc-agent-backend-dev-118078450167.us-east4.run.app/health
```
