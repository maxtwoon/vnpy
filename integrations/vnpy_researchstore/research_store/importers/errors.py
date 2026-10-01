"""Error types for the importer subsystem.

Importers never silently swallow failures: a failed member, table or archive
must surface as a distinct exception or counted failure so the caller can
record it in the batch receipt instead of pretending the neighbour members'
success covers it.
"""

from __future__ import annotations


class ImporterError(Exception):
    """Base class for all importer errors."""


class UnsafeMemberError(ImporterError):
    """An archive member failed safety validation (path traversal, absolute
    path, backslash, drive letter or symlink type)."""


class MissingDependencyError(ImporterError):
    """An optional decompression dependency is not installed in this
    interpreter (for example ``zstandard`` for ``.tar.zst`` archives)."""


class HashMismatchError(ImporterError):
    """Archive or file content hash differs from its recorded sidecar."""


class MemberReadError(ImporterError):
    """A single archive member could not be parsed. Other members are still
    processed; the failed member is reported individually."""


class SchemaMismatchError(ImporterError):
    """Source schema does not match the schema the adapter expects."""


class CaptureError(ImporterError):
    """Consistent SQLite capture of a mutable source database failed."""


class AmbiguousSymbolError(ImporterError):
    """A source symbol cannot be mapped to a unique instrument for the given
    date (for example three-digit Zhengzhou contract codes)."""
