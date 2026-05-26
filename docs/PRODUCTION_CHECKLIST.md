# Production Readiness Checklist

Use this checklist before promoting DICOM Toolkit App beyond local development.

## Application

- [ ] Set strong values for `JWT_SECRET_KEY`, `POSTGRES_PASSWORD`, and any API keys.
- [ ] Restrict `CORS_ORIGINS` to trusted origins.
- [ ] Confirm upload size limits match operational policy.
- [ ] Confirm failed jobs expose useful messages without leaking PHI.
- [ ] Confirm audit logging is retained according to policy.
- [ ] Confirm all public routes are intentional.

## Imaging

- [ ] Validate CT, MR, X-ray, ultrasound, secondary capture, and target formats in OHIF.
- [ ] Validate DICOMweb QIDO/WADO/STOW behavior through the proxy.
- [ ] Decide whether Orthanc is local-only or externally reachable.
- [ ] Enable Orthanc authentication for non-local deployments.
- [ ] Validate de-identification against required DICOM tags and private tags.

## Data And Backups

- [ ] Back up `postgres-data`.
- [ ] Back up `orthanc-storage`.
- [ ] Back up required export/output data from `api-output`.
- [ ] Test restore into a clean environment.
- [ ] Define retention and purge policies for uploaded and converted files.

## Operations

- [ ] Add centralized logs for proxy, API, worker, Orthanc, and database.
- [ ] Add uptime and job-failure alerts.
- [ ] Add disk-space alerts for archive and output volumes.
- [ ] Run dependency vulnerability scanning.
- [ ] Pin production image tags and application versions.

## Compliance

- [ ] Complete PHI handling review.
- [ ] Complete threat model.
- [ ] Complete validation protocol for clinical use.
- [ ] Confirm the app is not represented as a certified diagnostic device unless separately certified.
