"""Read and verify an explicitly named researchstore snapshot without following latest."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import research_store


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--snapshot-id', required=True)
    parser.add_argument('--dataset-id', required=True)
    parser.add_argument('--mapping', type=Path)
    args = parser.parse_args()
    if args.snapshot_id.lower() in {'latest', 'current'}:
        raise ValueError('An immutable snapshot ID is required')
    store = research_store.open_store(args.root)
    try:
        reader = research_store.open_snapshot(store, args.snapshot_id)
        try:
            rows = sum(batch.num_rows for batch in reader.bars(args.dataset_id,
                required_fields=(), allow_missing_auxiliary=True))
        finally:
            reader.close()
        result = {'snapshot_id': args.snapshot_id, 'dataset_id': args.dataset_id,
                  'rows': rows, 'source_mapping': 'missing'}
        if args.mapping:
            mapping = json.loads(args.mapping.read_text(encoding='utf-8'))
            if mapping['snapshot_id'] != args.snapshot_id or mapping['dataset_id'] != args.dataset_id:
                raise ValueError('Mapping target differs from requested snapshot')
            source = mapping['source']
            actual = hashlib.sha256(Path(source['manifest_path']).read_bytes()).hexdigest()
            if actual != source['manifest_sha256']:
                raise ValueError('Warehouse source manifest hash mismatch')
            capture = Path(mapping['result']['capture'])
            captured = json.loads(capture.read_text(encoding='utf-8'))
            captured_source = captured.get('bridge_provenance', captured['metadata']['warehouse_provenance'])
            if any(source.get(key) != value for key, value in captured_source.items()):
                raise ValueError('Mapping conflicts with captured source provenance')
            receipt = json.loads(Path(mapping['result']['receipt']).read_text(encoding='utf-8'))
            if hashlib.sha256(capture.read_bytes()).hexdigest() != receipt['capture_sha256']:
                raise ValueError('Captured source asset hash mismatch')
            result.update(source_mapping='verified', source=source,
                          mapping_sha256=hashlib.sha256(args.mapping.read_bytes()).hexdigest())
        print(json.dumps(result, ensure_ascii=False))
        return 0
    finally:
        store.close()


if __name__ == '__main__':
    raise SystemExit(main())
