# OHIF Integration Strategy

## Recommendation

For the first production-oriented release, keep the application integrated with OHIF through a pinned upstream version, but avoid making app-specific changes inside OHIF unless absolutely necessary.

The preferred long-term shape is:

- Treat OHIF as an upstream viewer dependency.
- Pin the exact upstream version or commit.
- Keep DICOM Toolkit runtime configuration in `infra/viewer/app-config.js`.
- Serve OHIF as its own static `viewer` service behind the root proxy.
- Keep app workflow code in `frontend/` and API orchestration code in `backend/`.

## Current Practical Choice

This repo does not vendor OHIF source or generated OHIF static assets. The local build script fetches official OHIF into an ignored external checkout and copies the built viewer into an ignored runtime directory:

```text
.external/ohif-viewer/
.runtime/ohif-dist/
```

To rebuild the viewer:

```powershell
.\scripts\build-ohif.ps1
```

## When To Move To A Separate Build

The current local workflow already keeps OHIF out of the committed source tree. Move from the local script to a dedicated viewer image or CI-produced static artifact when one of these becomes true:

- You want cleaner upstream OHIF upgrades.
- CI should build OHIF from an upstream tag instead of committed source.
- Multiple apps need the same viewer build.
- You need a formal dependency-review process around viewer updates.

For a production deployment, the separate viewer image is the cleanest end state. It lets the app deploy stable workflow/API changes independently from viewer upgrades while still keeping OHIF pinned and auditable. A Git submodule is not recommended for this app unless you need to inspect or patch OHIF source regularly; it still couples repo operations to upstream source checkout mechanics.

## What Not To Do

- Do not mix DICOM Toolkit workflow UI into OHIF source.
- Do not make local OHIF edits without documenting them as patches.
- Do not point production at a moving `latest` OHIF build.
- Do not commit generated OHIF `dist` output unless the release process explicitly requires immutable release artifacts.
