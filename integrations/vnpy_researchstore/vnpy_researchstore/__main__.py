"""Entry point for ``python -m vnpy_researchstore`` (recorder launcher).

The package import itself stays side-effect free; the launcher bootstrap
(isolated runtime dir, explicit repo binding) runs inside ``main``.
"""

from .launcher import main

if __name__ == "__main__":
    raise SystemExit(main())
