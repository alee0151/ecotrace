# EcoTrace Azure Deployment

## Recommended Azure Layout

- Frontend: Azure Static Web Apps
- Backend: Azure App Service for Linux, Python
- Database: existing Azure Database for PostgreSQL

## Backend: Azure App Service

Create a Linux Python App Service from the repo root.

Build settings:

```text
App root: repo root
Runtime: Python 3.12
Build command: pip install -r requirements.txt
Startup command: bash startup.sh
```

Required App Service application settings:

```env
DB_HOST=ecotrace-db.postgres.database.azure.com
DB_PORT=5432
DB_NAME=postgres
DB_USER=postgres
DB_PASSWORD=<secret>
DB_SSLMODE=require
CORS_ALLOW_ORIGINS=https://<your-static-web-app>.azurestaticapps.net
FRONTEND_BASE_URL=https://<your-static-web-app>.azurestaticapps.net
MAX_REPORT_UPLOAD_MB=25
WARM_IUCN_CACHE_ON_STARTUP=false
IUCN_CACHE_MAX_AGE_HOURS=168
EMAIL_DELIVERY_MODE=outbox
```

Add API keys and SMTP settings as needed. Do not commit real `.env` values.

After frontend deployment, update:

```env
CORS_ALLOW_ORIGINS=https://<frontend-url>
FRONTEND_BASE_URL=https://<frontend-url>
```

## Frontend: Azure Static Web Apps

Create a Static Web App connected to the GitHub repository.

Build settings:

```text
App location: fronend
API location: <blank>
Output location: dist
Build command: npm run build
```

Frontend environment variable:

```env
VITE_API_BASE_URL=https://<your-backend-app>.azurewebsites.net
```

The file `fronend/staticwebapp.config.json` handles React Router fallback for routes such as `/app/spatial` and `/app/verify-email`.
