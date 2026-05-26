# Running Locally On Windows 11

These steps assume Docker Desktop is installed and running.

## Start

```powershell
cd "C:\Users\Laith\OneDrive\Desktop\DICOM toolkit with a viewer"
.\scripts\start-local.ps1
```

The helper script builds OHIF into `.runtime\ohif-dist` if the viewer assets are missing, then starts Docker Compose. To run Compose directly, build the viewer first:

```powershell
.\scripts\build-ohif.ps1
docker compose up -d --build
```

Open:

```text
http://localhost:8080
```

## Verify

```powershell
docker compose ps
Invoke-WebRequest -UseBasicParsing http://localhost:8080/api/v1/health/live
Invoke-WebRequest -UseBasicParsing http://localhost:8080/app-config.js
```

## Common Commands

```powershell
docker compose logs -f api
docker compose logs -f worker
docker compose logs -f proxy
docker compose logs -f orthanc
docker compose up -d --force-recreate viewer proxy orthanc
docker compose down
```

## Browser Cache After OHIF Changes

If OHIF shows a blank or black page after viewer configuration changes:

1. Open DevTools.
2. Go to **Application**.
3. Select **Storage**.
4. Click **Clear site data**.
5. Unregister any service worker for `localhost:8080`.
6. Reload or use an Incognito window.

## Reset Local Data

This removes local database, archive, Redis, and output volumes.

```powershell
docker compose down -v
docker compose up -d --build
```
