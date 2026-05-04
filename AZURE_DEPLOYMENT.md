# EcoTrace Azure Deployment

This repo deploys as two separate Azure resources:

- Frontend: Azure App Service for Linux/Node from `fronend`
- Backend: Azure App Service for Linux/Python from `backend`
- Database: Azure Database for PostgreSQL, configured through backend app settings

Note: the frontend folder is currently named `fronend`, so the workflow paths use that spelling.

## Files Added

- `.github/workflows/deploy-frontend-app-service.yml`
- `.github/workflows/deploy-backend-app-service.yml`
- `fronend/server.js`
- `fronend/.env.production.example`
- `backend/azure-app-settings.example.env`
- `startup.sh`
- `requirements.txt`
- `runtime.txt`

## 1. Create Azure Resources

Create these in the same resource group:

1. Azure App Service for the frontend.
   - Publish: Code
   - Runtime stack: Node 22 LTS
   - OS: Linux
2. Azure App Service for the backend.
   - Publish: Code
   - Runtime stack: Python 3.12
   - OS: Linux
3. Azure Database for PostgreSQL, if you are not already using one.

Recommended names:

```text
ecotrace-frontend
ecotrace-backend
ecotrace-db
```

## 2. Configure Backend App Service

In Azure Portal, open the backend App Service, then set:

Settings > Configuration > General settings > Startup Command:

```bash
bash startup.sh
```

Settings > Environment variables:

Use `backend/azure-app-settings.example.env` as the template.

Important values:

```env
SCM_DO_BUILD_DURING_DEPLOYMENT=true
ENABLE_ORYX_BUILD=true
CORS_ALLOW_ORIGINS=https://seeco-frontend-h9hxagc8hvhffegt.australiaeast-01.azurewebsites.net
FRONTEND_BASE_URL=https://<your-frontend-app>.azurewebsites.net
```

For Resend email delivery:

```env
EMAIL_DELIVERY_MODE=smtp
EMAIL_PROVIDER=resend
RESEND_API_KEY=<your-resend-api-key>
REPORT_FROM_EMAIL=noreply@<your-verified-domain>
REPORT_FROM_NAME=EcoTrace
SMTP_PORT=587
SMTP_USE_TLS=true
SMTP_USE_SSL=false
```

The `REPORT_FROM_EMAIL` domain must be verified in Resend. Resend SMTP uses `smtp.resend.com`, username `resend`, and your API key as the password; the app fills those values automatically when `EMAIL_PROVIDER=resend` is set.

The backend workflow deploys `backend`, `config`, `startup.sh`, `runtime.txt`, and the root `requirements.txt`. The root requirements file points Azure to `backend/requirements.txt`.

## 3. Add GitHub Secrets and Variables

In GitHub, open:

Settings > Secrets and variables > Actions

Add this repository variable:

```text
AZURE_BACKEND_WEBAPP_NAME=<your-backend-app-service-name>
AZURE_FRONTEND_WEBAPP_NAME=<your-frontend-app-service-name>
```

Add these repository secrets:

```text
AZURE_BACKEND_PUBLISH_PROFILE=<contents of backend App Service publish profile>
AZURE_FRONTEND_PUBLISH_PROFILE=<contents of frontend App Service publish profile>
VITE_API_BASE_URL=https://<your-backend-app>.azurewebsites.net
```

Where to get them:

- Backend publish profile: Azure App Service > Overview > Download publish profile.
- Frontend publish profile: frontend App Service > Overview > Download publish profile.

For publish-profile deployment, Azure App Service basic authentication must be enabled. If the publish profile download is unavailable for a Linux app, add `WEBSITE_WEBDEPLOY_USE_SCM=true` in the App Service environment variables, save, then retry the download.

## 4. Configure Frontend App Service

In Azure Portal, open the frontend App Service, then set:

Settings > Configuration > General settings > Startup Command:

```bash
npm start
```

Settings > Environment variables:

```text
SCM_DO_BUILD_DURING_DEPLOYMENT=false
WEBSITE_NODE_DEFAULT_VERSION=~22
```

The frontend workflow builds the Vite app in GitHub Actions, then deploys only `dist`, `server.js`, and `package.json` to the frontend App Service. `fronend/server.js` serves static assets and falls back to `index.html` for React Router routes.

The frontend build needs:

```env
VITE_API_BASE_URL=https://<your-backend-app>.azurewebsites.net
```

## 5. Push to GitHub

Commit and push the deployment files to `main`:

```bash
git add .github/workflows AZURE_DEPLOYMENT.md backend/azure-app-settings.example.env fronend/.env.production.example
git add .gitignore fronend/package.json fronend/server.js
git rm .github/workflows/deploy-frontend-static-web-app.yml fronend/staticwebapp.config.json
git rm --cached .DS_Store fronend/.DS_Store
git commit -m "Add Azure deployment workflows"
git push origin main
```

After the push:

1. GitHub Actions runs `Deploy Backend - Azure App Service` when backend files change.
2. GitHub Actions runs `Deploy Frontend - Azure App Service` when frontend files change.
3. You can also run either workflow manually from GitHub Actions > workflow > Run workflow.

## 6. Verify Deployment

Backend:

```text
https://<your-backend-app>.azurewebsites.net/health
```

Frontend:

```text
https://<your-frontend-app>.azurewebsites.net
```

If the frontend loads but API calls fail, check:

- `VITE_API_BASE_URL` in GitHub secrets points to the backend URL.
- `CORS_ALLOW_ORIGINS` in backend App Service contains the frontend URL exactly.
- Backend App Service logs show Gunicorn starting `backend.main:app`.

## 7. Azure CLI Alternative

You can set the backend startup command from Azure Cloud Shell:

```bash
az webapp config set \
  --resource-group <resource-group-name> \
  --name <backend-app-service-name> \
  --startup-file "bash startup.sh"
```

Restart after changing configuration:

```bash
az webapp restart \
  --resource-group <resource-group-name> \
  --name <backend-app-service-name>
```
