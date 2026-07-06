#!/usr/bin/env bash
# Lanzador de la app de escritorio. Activa el venv si existe y abre la ventana.
set -e
cd "$(dirname "$0")"

if [ -d ".venv" ]; then
    # shellcheck disable=SC1091
    source .venv/bin/activate
fi

exec python app.py
