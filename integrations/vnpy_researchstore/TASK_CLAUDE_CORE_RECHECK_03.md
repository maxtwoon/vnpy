# Actual Claude Code focused core recheck03

Dispatch only after the actual developer finishes TASK_OPENCODE_CORE_FIX_03.md (functional TASK_KIMI_CORE_FIX_03.md), supplies .coordination/opencode-core-fix03-handoff.md, and Codex confirms no core writer. Read CORE_AUDIT_02.md, CORE_AUDIT_02_DISPOSITION.md, that handoff and changed INTERFACES. Reuse prior valid evidence for unchanged code; this is a focused closure of F1/F2/F3 and affected regression behavior, not a new whole-system audit.

No product edits. Actual Kimi/OpenCode develops; Codex coordinates. Use the package .venv, scoped tests and temporary repros under .coordination/review-core03. No raw/source provider/credentials/account/gateway/default settings/ledger/vnpy core/site-packages/git writes. Do not scan CLI transcripts as source. Record reviewed file hashes and exact commands/results.

F1: using only the public conflict receipt and public store APIs, import conflicting minute AND daily rows, obtain real bounds, quarantine, fail on an intersecting unallowed query, then explicitly allow the real gap and query without filler. Check receipt serialization/recovery preserves the new field. No private-sidecar parsing or guessed1ns workaround. Consumer-owned overlay test should use the public contract after its own owner updates it; distinguish pending caller work from a remaining core defect.

F2: rerun prior reviewer repro_multipartition.py and adapt it only to the fixed public API if needed. Interrupt after one partition commits; batch cannot claim whole publication. General recover() must surface the partially published FAILED batch, safely recover when durable anchors allow or explicitly report why it cannot. Test repeated recovery/same-input retry and a missing/tampered anchor; do not lose the prior committed partition, duplicate rows, clobber a new head or silently succeed.

F3: same instrument/same nanosecond timestamp with two different stable event identities preserves both, even for equal market fields; repeated same-event input is idempotent; changed payload under reused identity is rejected/conflicted. Validate required identity and original precision, snapshot readback and deterministic ordering across batches/sessions. No timestamp-derived sequence or native tick-backtesting scope expansion. Check daily identity and minute NULL-day behavior remain intact.

Review the developer's exact declared key against the session/ingest-sequence contract, including whether reusing the same session/sequence with a changed instrument or timestamp can be silently accepted as a different event. Distinguish canonical deterministic read order from the later recorder replay requirement of event-time plus sequence ordering; recording remains subsequent work. This is part of F3 closure, not scope expansion.

Run affected tests, core typing/lint and pure import check; use exact-code previous results where no new risk exists. Do not rerun unrelated native/importer or archived suites. Return per-finding CLOSED/OPEN with evidence, any directly introduced regression, and PASS/FAIL for corrected core. Recording journal/seal remains a subsequent milestone and must not be declared complete here.

Do not create, update or append ANY assistant/project memory (including .claude/projects/**/memory, .codex/memories or MEMORY.md). The user has not requested memory updates. Save task evidence only in the explicitly named review artifact directory; an auto-memory habit does not authorize extra writes.

