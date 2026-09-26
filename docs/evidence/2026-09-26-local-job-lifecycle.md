# Local analysis job lifecycle

Completed jobs previously retained cancellation events and snapshot-to-job entries in memory. Queue capacity checks revisited all retained jobs. Restarting the runtime discarded the deduplication map, so requesting the same snapshot started another analysis despite the persisted completed job.

The runtime now looks up the latest attempt by repository and snapshot in SQLite, using a supporting index. Non-failed/non-cancelled attempts retain the previous reuse semantics across runtime restarts. Failed and cancelled attempts may retry. Only active cancellation events remain in memory; success, worker failure, and executor submission failure release them. Queued cancellations still occupy capacity until processed, preserving the bounded executor queue.

Verification: two regression tests first reproduced retained success/failure events. The corrected full backend suite passed **331 tests**, with **37 PostgreSQL-dependent skips** and one existing Starlette/httpx deprecation warning. Checks include actual static analysis and reopened-store reuse, failure retry, rejected executor submission, queue limits, and latest-attempt isolation across repositories and snapshots. Updating an older job does not make it the latest attempt.

No imported code was executed. Existing analysis reports and source snapshots are preserved. A completed analysis is reused for the same snapshot; this does not introduce a force-reanalysis control or analyzer-version cache invalidation.
