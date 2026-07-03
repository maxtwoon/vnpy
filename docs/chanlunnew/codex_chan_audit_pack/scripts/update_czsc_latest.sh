#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON_VERSION="${PYTHON_VERSION:-3.12}"
VENV_PATH="${VENV_PATH:-.venv-czsc-rc8}"

command -v uv >/dev/null 2>&1 || {
  echo "uv is required: https://docs.astral.sh/uv/getting-started/installation/" >&2
  exit 1
}

export UV_CACHE_DIR="$ROOT/.uv-cache"
export UV_PYTHON_INSTALL_DIR="$ROOT/.uv-python"

uv venv "$VENV_PATH" --python "$PYTHON_VERSION" --clear

if [[ "$OSTYPE" == msys* || "$OSTYPE" == cygwin* ]]; then
  VENV_PYTHON="$VENV_PATH/Scripts/python.exe"
else
  VENV_PYTHON="$VENV_PATH/bin/python"
fi

uv pip install --python "$VENV_PYTHON" --upgrade --prerelease=allow "czsc==1.0.0rc8"
"$VENV_PYTHON" -c "import sys, czsc, importlib.metadata as m; print('python:', sys.version); print('czsc:', m.version('czsc')); print('czsc file:', czsc.__file__)"
"$VENV_PYTHON" scripts/verify_runtime_with_czsc.py

echo "czsc 1.0.0rc8 environment is ready: $VENV_PYTHON"
