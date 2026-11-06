# Event/FSM v1 implementation

The normative source is `docs/superpowers/specs/2026-11-06-dsh-plugin-design.md` §5–7. JSON schema: `event-schema.json`; HTTP defaults to `127.0.0.1:17321`. USB remains `usb-protocol-v1.md`.

Identity: agent + producer scope; session generation is instance_seq, runtime handover is runtime_seq + runtime_ready. IDs are opaque; wall clock and UUID ordering do not establish generations. Only after a runtime_ready barrier can healthy withdraw a recovering fault. Pending identity is not final ACK.

Base state: turn_start at a higher turn clears prior terminal state. Same turn has ERROR > COMPLETED > CANCELLED > RUNNING. Cancellation contributes IDLE. Activity cannot clear terminal state or waits. Only completed opens a persisted completion deadline, once. Disposed removes waits and ordinary completion/running; an explicit error persists.

Wait identity is attention_id + original turn_seq/turn_id within producer/session/instance. Precise resolve can close an earlier turn. Resolve tombstones suppress later opens. Bootstrap opens use turn_seq=0, turn_id=bootstrap before first real turn. Higher turns do not close waits.

Display: ERROR > ATTENTION > RUNNING > COMPLETED > IDLE across all sources. Recovering/degraded or a 15-second lease expiry contributes an independent ERROR, never a fabricated chat failure. Server restart grants all known sources a fresh 15-second registration window; already degraded sources remain visibly degraded.

Final event responses follow durable SQLite commit: applied, duplicate or stale. Same identity/different body is 409. 202 pending_identity must be retried. Body allowlist rejects content fields; no conversation text enters storage or USB.
