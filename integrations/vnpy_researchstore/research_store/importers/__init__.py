"""Importer subpackage for the research store.

Owned by the OpenCode import workstream (WP03/WP04/WP06 import side).
Pure stdlib + optional ``zstandard``/``pyarrow``; never imports vnpy or any
provider SDK.
"""

from .adapters import (
    import_jq_daily,
    import_rq_etf,
    import_rq_futures,
    import_ssquant_table,
)
from .dominant_map import (
    ContractDateMapper,
    DominantMapping,
    build_dominant_mapping,
    load_dominant_mapping,
    save_dominant_mapping,
)
from .errors import (
    AmbiguousSymbolError,
    CaptureError,
    HashMismatchError,
    ImporterError,
    MemberReadError,
    MissingDependencyError,
    SchemaMismatchError,
    UnsafeMemberError,
)
from .inventory import scan_directory, scan_rq_package, scan_source_roots
from .partitions import bucket16, partition_for_row, product_of
from .readers import iter_tar_zst_csv, iter_tar_zst_parquet
from .repair_index import load_repair_index
from .safeio import iter_gzip_csv_chunks, verify_sha256_sidecar
from .sink import CountingSink, ImportSink, JSONLImportSink
from .sqlite_source import (
    build_table_plan,
    capture_sqlite,
    connect_read_only,
    simnow_quarantine_keys,
)
from .store_sink import StoreSink, candidate_reason_counts, iter_candidates
from .time_evidence import (
    LabelEvidence,
    LabelEvidenceError,
    LabelProfile,
    build_label_evidence,
)

__all__ = [
    "AmbiguousSymbolError",
    "CaptureError",
    "ContractDateMapper",
    "CountingSink",
    "DominantMapping",
    "HashMismatchError",
    "ImportSink",
    "ImporterError",
    "JSONLImportSink",
    "LabelEvidence",
    "LabelEvidenceError",
    "LabelProfile",
    "MemberReadError",
    "MissingDependencyError",
    "SchemaMismatchError",
    "StoreSink",
    "UnsafeMemberError",
    "bucket16",
    "build_dominant_mapping",
    "build_label_evidence",
    "build_table_plan",
    "candidate_reason_counts",
    "capture_sqlite",
    "connect_read_only",
    "import_jq_daily",
    "import_rq_etf",
    "import_rq_futures",
    "import_ssquant_table",
    "iter_candidates",
    "iter_gzip_csv_chunks",
    "iter_tar_zst_csv",
    "iter_tar_zst_parquet",
    "load_dominant_mapping",
    "load_repair_index",
    "partition_for_row",
    "product_of",
    "save_dominant_mapping",
    "scan_directory",
    "scan_rq_package",
    "scan_source_roots",
    "simnow_quarantine_keys",
    "verify_sha256_sidecar",
]
