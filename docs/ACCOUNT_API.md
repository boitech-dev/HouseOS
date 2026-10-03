# Account controls

Registered by `houseos.account.router`; all routes require the current authenticated
actor and mutation CSRF. No administrator can supply another user's ID.

- `GET /account/profile`: own ID, display name, username, language, avatar and memory toggle.
- `PATCH /account/profile`: optional `name` (1–80 visible characters), `language`
  (`en|fr|es`), `avatar` (`crest|moon|raven|bat|rose|ghost`), `memory_enabled` (boolean).
  Other preferences remain intact; unknown fields are rejected.
- `GET /account/export`: downloadable JSON, `Cache-Control: no-store`. Streams all
  qualifying own rows with 200-row keyset pages, rather than truncating to a UI limit.
  Includes settings, memories (including expired memories), conversations and messages,
  authored household records, named-recipient messages, saved music/playlists, file
  metadata, Cinema state/preferences and usage. Excludes file bytes, credential hashes,
  session tokens, provider secrets and other residents' private data. The export is a
  live read, not a database snapshot. The trailing `complete:true` exists only after all
  sections finish; session revocation interrupts the stream.
- `PUT /assistant/memories/{id}`: replace an owned explicit memory using the normal
  memory schema; an optional expiry must include a timezone. Memory disabling stops
  context injection and new saves, while existing memories remain visible for manual
  edit/delete/export.
- `POST /account/delete/prepare` with `{current_password}`: exact impact counts and
  a two-minute actor-bound confirmation. No account mutation occurs here.
- `POST /account/delete/confirm/{id}` with `{current_password}`: reauthenticates,
  verifies the unchanged private-data fingerprint and checks the last-admin invariant.
  Active uploads must finish or be cancelled first. New reservations are serialized
  with deletion through the quota lock and fresh owner state.

Deletion revokes every session, disables push, revokes unused invitations created by
that account, cancels pending jobs, marks running jobs unverified, and clears personal
assistant history, memories, saved library state and Cinema preferences/history.
Personal files move to Trash and their grants are revoked; this is not physical erasure.
Shared records/files and delivered messages remain, attributed to a former resident.
Sanitized operational/audit/usage records and protected backups follow their retention
policies. Already-running physical playback may continue. The interface discloses these
limits before confirmation; no existing account was deleted during development.
