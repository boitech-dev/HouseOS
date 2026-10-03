# Household and files API

All paths prefixed `/api/v1`. Cookie auth + CSRF on mutations. Errors use `detail`;
409 means refresh/conflict/review, 503 means storage/transport unavailable.

## Household (implemented contract)

Kinds: `board`, `tasks`, `groceries`, `calendar`, `messages`, `captures`.
- GET `/household/{kind}?q=&limit=100&offset=0` → `{items:[{id,kind,owner_id,data,version,created_at,updated_at}],offset,limit}`.
- POST `/household/{kind}` `{data:{...},idempotency_key:"UUID",allow_duplicate:false}` → record. Retry same key safely. Grocery duplicate → 409 `{code:DUPLICATE_REVIEW,candidate_ids,message}`; show review and intentional add option with allow_duplicate=true and a new key.
- GET `/household/{kind}/{id}` → record.
- PATCH same path `{version:1,data:{changed fields}}` → new record/version.
- DELETE same path `?version=1` → soft-delete. Author/admin only; sent messages immutable.
- POST `/household/tasks/{id}/action` `{version,action:claim|complete|snooze|reassign|decline,assignee_id?,due_date?}`.
- POST `/household/groceries/{id}/undo` `{version}`.
- GET `/household/inbox?unread=false` → `{items:[{id,record_id,category,created_at,read_at}]}`.
- POST `/household/inbox/{id}/read` → private read state, not exposed to senders.

Data shapes (extra fields rejected):
- board: title, body, pinned=false, importance=normal|important|urgent, expires_at nullable timezone-qualified ISO timestamp, resolved=false, attachments=[] file IDs.
- tasks: title, note, assignee_id nullable, due_date YYYY-MM-DD nullable, due_time HH:MM nullable, timezone IANA name (default: the house's time zone), fold 0|1 nullable, status open|in_progress|done|cancelled, recurrence daily|weekly|monthly|null. Server-produced template_id identifies occurrence; don't submit it.
- groceries: label, quantity/string, unit/string, category/string, note/string, purchased=false. Purchased attribution/time and undo are server-owned; don't resubmit those fields.
- calendar: title, all_day=false, start/end (date for all-day, local ISO datetime for timed), timezone IANA name (default: the house's time zone), start_fold/end_fold nullable, location, notes, participants=[] user IDs, reminder_minutes=[], recurrence daily|weekly|monthly|null. All-day end is exclusive. Ambiguous local times return 422 until fold chosen; nonexistent local times rejected.
- messages: body, recipient_ids=[user IDs], attachments=[], sent_with_assistant=false. No broadcast wildcard. Attachments require pre-existing explicit recipient grants.
- captures: text, url nullable. No server fetch or automatic action.

All private queries/events are actor/recipient scoped. Expired ordinary board notes excluded by default; urgent issues remain until resolved. Recurrence is template + separate occurrences, never shared completion state.

## Files (implementation in progress; stable frontend contract)

- GET `/files?scope=personal&parent_id=&q=` → `{items:[{id,name,is_folder,scope,parent_id,owner_id,size,mime,version,trashed_at,created_at}], ...}`. scopes personal|house|drop|media|shared|trash.
- POST `/files/folders` `{name,scope:"personal",parent_id:null,idempotency_key:"UUID"}` → entry.
- PATCH `/files/{id}` `{version,name?,parent_id?}` → entry; same-scope move only.
- GET `/files/{id}/download` authenticated attachment, streaming.
- GET `/files/{id}/preview` safe raster/media types only; HTML/SVG/executable content never inline.
- POST `/files/{id}/actions/prepare` `{version,action:"trash"|"restore"|"share"|"unshare"|"scope",recipient_id?,scope?}` → `{confirmation_id,preview,expires_at}`.
- POST `/files/confirmations/{confirmation_id}` empty body executes exact stored actor/version-bound preview; invalid/stale/expired/replayed confirmations fail.
- GET `/files/quota` → `{used_bytes,reserved_bytes,quota_bytes,max_upload_bytes,storage_status}`.
- POST `/files/uploads` `{name,size,scope:"personal",parent_id:null,idempotency_key:"UUID"}` → `{id,status,upload_url,offset,size,expires_at}`.
- GET `/files/uploads/{id}` → same status; `status=stored` includes `file` metadata.
- HEAD `upload_url` with `Tus-Resumable: 1.0.0` → Upload-Offset, Upload-Length.
- PATCH `upload_url` with CSRF, Tus-Resumable, Upload-Offset, Content-Type application/offset+octet-stream and bounded Blob chunks (<=16 MiB). Headers/offset follow tus1.0. Explicit Content-Length supplied by browser for Blob body. Final PATCH byte acceptance is not storage completion.
- POST `/files/uploads/{id}/finalize` → `{status:"stored",file:...}` only after fsync, hash, atomic same-filesystem rename and DB commit. Retry safely after interruption.
- DELETE `upload_url` → cancellation, server cleanup and quota release.

Resume by retained upload ID + HEAD; expiry is 24h. Keep page open during upload; offline/closed-browser background transfer isn't promised. My Files is default. Upload success UI must wait for finalize. No public share URLs or arbitrary filesystem paths.

## Expanded household operations

- POST `/household/groceries/batch` `{items:[{id,version}],purchased,idempotency_key}` atomically applies the exact reviewed list; returns `undo_id` and new versions.
- POST `/household/groceries/undo-batch/{undo_id}` restores that actor's exact batch within five minutes; any intervening edit blocks the whole undo.
- GET `/household/calendar/agenda?start=YYYY-MM-DD&end=YYYY-MM-DD` expands daily/weekly/monthly events up to a year, preserving wall times in the house's time zone across DST. `schedule_error=DST_REVIEW_REQUIRED` excludes unresolved instants from reminders/export.
- GET `/household/calendar/export.ics` exports explicit occurrences over a bounded past30days/next366days window.

## Drop expiry, bulk operations and permanent removal

Folder/upload creation accepts `expires_hours` (1–720), effective only for Drop; default7days. Expiry first moves to recoverable trash, retaining quota and bytes. Restoring an expired drop renews it for7days.

`POST /files/bulk/prepare` accepts `{items:[{id,version}],action:"trash"|"restore"|"purge"}`. The preview contains the exact expanded target list, count, bytes and irreversible flag. Maximum500entries, then ask for a smaller selection. `POST /files/confirmations/{id}` executes that exact scope; changes invalidate it. Purge requires Trash first, unlinks only opaque app-owned files, fsyncs the directory and retains tombstones/progress for interrupted-operation recovery. Replay after completion is rejected. Folder contents added after preview invalidate it.

Single-file prepare supports `purge` too. Folder trash/restore is automatically routed through an exact bulk preview.

`GET /files/admin/policy` and reauthenticated `PUT /files/admin/policy` `{permanent_delete_enabled,trash_retention_days:30..365,current_password}` configure retention. Irreversible scheduled cleanup starts disabled; enabling it is an explicit admin action. There is no silent deletion of old files before this configuration.

## Selected existing roots (read-only)

- GET `/files/roots` returns `{items:[{id,name,read_only:true,version}]}` filtered by explicit readers.
- Admin POST `/files/roots/prepare` `{name,path,reader_ids:[],current_password}` validates exactly a selected existing subdirectory of `/mnt/house-storage/media`, outside HouseOS's own byte store, on the approved storage filesystem. No recursive scan. Empty readers means all residents with file access and is explicit in the preview.
- Admin POST `/files/roots/confirm/{confirmation_id}` registers that exact preview.
- GET `/files/roots/{id}/entries?directory_id=&offset=0` returns at most200 entries plus next_offset, parent_id. Names are labels; IDs are authenticated encrypted references expiring after1hour. Hidden/symlink/special entries are omitted. No arbitrary relative path arguments.
- GET `/files/roots/{id}/download?file_id=...` authorizes and opens every component with nofollow, regular files only, with range support and attachment disposition.
- Admin DELETE `/files/roots/{id}?version=...` revokes access and existing tokens; existing bytes remain untouched.

## Browser push

- GET `/notifications/push` -> configuration/public VAPID key, current actor's subscription IDs, preferences, honest in-app-only delivery guarantee.
- POST `/notifications/push` accepts browser subscription.toJSON() (`endpoint`, `keys`, `expirationTime`). Call only after user opt-in. Subscription endpoint/keys encrypted at rest; never returned by read endpoints.
- DELETE `/notifications/push/{id}` revokes own device subscription; other account IDs return404.
- PUT `/notifications/preferences` `{quiet_start:"23:00",quiet_end:"08:00",timezone:"UTC",muted_categories:[]}` (timezone optional; default: the house's time zone).

Push payload is `{title:"MIDNIGHT HOUSE",body:"New house message",url:"/#household",tag:"house-inbox"}`. A provider-accepted delivery is neither displayed nor read. Quiet hours suppress external sends only; inbox always persists. Browser/push provider availability and a configured VAPID identity remain real-device gates.

## Worker hooks

Run `household.maintain_household(db)` and `files.maintain_files(db)` about every60seconds, `await files.expire_uploads(db)` for abandoned transfers, `notifications.deliver_pending(db,limit=10)` outside audio control. Each returns bounded counts; no LLM. Lost push network outcomes stay unverified instead of blindly retrying.

## Assistant bundle coverage

`tool_household.build_tools("household")` supplies10 typed tools: scoped reads, resident lookup, typed board/task/grocery/calendar/capture creation, typed versioned edits with explicit nullable-field clearing, task actions, exact grocery batch/undo, calendar agenda, message preparation and private inbox. `build_tools("files")` supplies7 tools: scoped metadata search, folder creation, same-scope move/rename, consequential-action preview, allowed read-only roots, quota and resident lookup. File content and privileged root/retention configuration are deliberately absent from the model tool bundle. Ordinary UI remains authoritative for exact confirmations.

## File list pagination

`GET /files` accepts `offset` (default 0, maximum 100000) in addition to `limit`.
Results use deterministic folder/name/ID ordering and return `next_offset` or null.
Authorization and ancestor visibility are still checked for every returned entry.

## House library: saved films in a browser

- `GET /files/library/films/{id}/browser` checks once whether a saved film plays in a browser as
  it is (H.264/VP8/VP9/AV1 picture, AAC/MP3/Opus/Vorbis/FLAC sound, MP4/WebM/Matroska file):
  `{playable, stream, reason}`. Nothing is converted; a film that does not qualify is sent to the TV.
- `GET /files/library/films/{id}/stream` serves it with byte ranges (residents only).
- The Files page lists "House" with the drop area merged in: `scope=drop` files are house files
  marked temporary (gone after 7 days).
