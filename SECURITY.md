# Security Policy

## Supported Status

This project is under active refactor toward a production-ready release. Until a `1.0.0` release is tagged, treat deployments as pre-production unless your organization has completed its own validation, threat model, privacy review, and regulatory assessment.

## Reporting A Vulnerability

Please report suspected vulnerabilities privately to the repository owner. Include:

- Affected component: backend, frontend, OHIF viewer, Orthanc, Docker/infra, or documentation.
- Steps to reproduce.
- Expected and actual behavior.
- Any relevant logs with secrets, tokens, and PHI removed.

## Security Expectations

- Never commit `.env` files, private keys, API keys, JWT secrets, certificates, or real patient data.
- Rotate `JWT_SECRET_KEY`, database passwords, and any API keys before production use.
- Put TLS, authentication, authorization, audit retention, backup, monitoring, and PHI handling under your organization-specific controls.
- Review Orthanc authentication and network exposure before deploying outside local development.
- Validate all conversion/de-identification behavior against your clinical and regulatory requirements.

## Local Development Defaults

The Docker Compose defaults are designed for local development on `localhost:8080`. They are not secure production defaults. Production deployments should use externally managed secrets, restricted CORS, HTTPS-only cookies, authenticated DICOMweb access, durable backups, and least-privilege network access.
