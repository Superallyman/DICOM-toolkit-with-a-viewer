#!/bin/sh
set -e

# --- Prepare OHIF working directory ---
# If a host-built read-only dist is mounted at $OHIF_RO_SRC, copy it once into writable /app/ohif
if [ -d "${OHIF_RO_SRC}" ] && [ -n "$(ls -A "${OHIF_RO_SRC}" 2>/dev/null)" ]; then
  if [ ! -f /app/ohif/.populated ]; then
    echo "[entrypoint] Populating /app/ohif from ${OHIF_RO_SRC} ..."
    rm -rf /app/ohif/* 2>/dev/null || true
    cp -a "${OHIF_RO_SRC}/." /app/ohif/
    touch /app/ohif/.populated
  fi
fi

# Ensure persistent studies dir exists
mkdir -p "${PERSISTENT_OUTPUT_DIR}/studies"

# Symlink viewer's studies folder to the persistent location
if [ ! -L /app/ohif/studies ]; then
  rm -rf /app/ohif/studies 2>/dev/null || true
  ln -s "${PERSISTENT_OUTPUT_DIR}/studies" /app/ohif/studies
fi

# --- DB migrations (optional but recommended) ---
if [ "${RUN_MIGRATIONS:-true}" != "false" ] && [ -f /app/alembic.ini ] && [ -d /app/alembic ]; then
  alembic -c /app/alembic.ini upgrade head
fi

# --- Launch app ---
exec "$@"
