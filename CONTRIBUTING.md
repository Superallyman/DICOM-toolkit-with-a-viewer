# Contributing

Thanks for helping improve DICOM Toolkit App. This repository is organized as a production-style monorepo with clear ownership boundaries between the web shell, API control plane, imaging archive configuration, worker processing, and OHIF runtime integration.

## Development Workflow

1. Create a focused branch from `main`.
2. Keep changes scoped to one concern where possible.
3. Run the local checks before opening a pull request:

```powershell
docker compose config --quiet
cd backend
python -m pytest
cd ..\frontend
npm run build
```

4. Include a short summary, testing notes, and screenshots for UI changes.

## Code Standards

- Keep API routes thin. Put workflow logic under `backend/app/domain`.
- Keep external integrations under `backend/app/infrastructure`.
- Use the worker for long-running conversion and ingest work.
- Keep OHIF-specific launch and DICOMweb behavior centralized in helper modules.
- Do not commit generated medical files, PHI, local volumes, `.env` files, or build artifacts.
- Preserve the separation between the Next.js workflow app and the OHIF diagnostic viewer.

## Medical Data

Do not commit real patient data. Use synthetic or properly de-identified test fixtures only. Treat uploaded DICOM, MIME, EML, image, and export files as sensitive by default.

## Pull Request Checklist

- [ ] The stack still starts with Docker Compose.
- [ ] Relevant backend tests pass.
- [ ] The frontend builds.
- [ ] New or changed environment variables are documented in `.env.example`.
- [ ] DICOMweb/OHIF viewer launch still works for converted studies.
- [ ] Security-sensitive changes were reviewed for PHI and auth impact.
