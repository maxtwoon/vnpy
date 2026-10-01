"""Test bootstrap for the import workstream test modules.

Adds the integration root to ``sys.path`` so ``research_store.importers``
resolves via PEP 420 namespace-package semantics even before the core
workstream adds ``research_store/__init__.py``. Once the package is properly
installed this becomes a no-op. Deliberately NOT a conftest plugin: the
common tests/conftest.py belongs to the core workstream.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ZSTANDARD_AVAILABLE = True
try:
    import zstandard  # noqa: F401
except ImportError:  # pragma: no cover
    ZSTANDARD_AVAILABLE = False

PYARROW_AVAILABLE = True
try:
    import pyarrow  # noqa: F401
except ImportError:  # pragma: no cover
    PYARROW_AVAILABLE = False
