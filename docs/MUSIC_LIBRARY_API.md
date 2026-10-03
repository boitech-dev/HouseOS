# Music API

All routes use /api/v1/music, current session permissions and CSRF.

- GET /library/playlists returns own named playlists. POST accepts {name,item_ids} for
  up to 50 validated remote queue items. POST /library/playlists/{id}/preview produces
  the existing playlist confirmation; DELETE removes only the caller's saved list.
- POST /local/preview {file_id,idempotency_key} explicitly explains that an authorized
  personal file's title/sound will be shared on household speakers. POST
  /local/{confirmation_id}/confirm consumes that exact file/version approval once.
  Original file grants remain unchanged; provider/filesystem paths are never exposed.
- Local audio is limited to 500 MiB input, four hours, one preparation, 4 GiB free disk
  headroom and a 10 GiB cache. It is copied with no-follow file descriptors, verified against
  size/hash and processed in the same isolated no-network/no-secret parser sandbox as Cinema.
  Canonical FLAC reaches mpv.
- Queue rows expose requires_approval and is_live. Tracks longer than 90 minutes need no
  approval: they stream to the speakers instead of downloading. Tracks over four hours fail
  with TRACK_TOO_LONG.
- POST /queue/{id}/approve-live {expected_version} explicitly authorizes a live item (a live
  YouTube stream, for example; a radio station started from Radio needs no approval)
  for one hour/400 MiB, with seeking disabled. POST /queue/{id}/renew-live extends the
  current lease by up to one hour; control permission and current queue generation are
  required. The initial approval expires if the queue does not start it within an hour.
- POST /queue/{id}/skip-vote {expected_version} returns {votes,threshold:3,status}.
  Three distinct current users with valid queue permission/session within five minutes
  create one authorized skip operation. Revocation invalidates a counted vote before
  execution. Arbitrary control capability is never granted to a guest.

## Queue order, moves and vetoes (`music.py`)

Every queue write takes `expected_version` and returns the new `version`; a stale version gets
409 `STALE_QUEUE` (with the current version). `GET /music` returns the queue with `fair`
(House setting "Take turns"), `veto_back_at` (null when your veto is ready) and `last_veto`
(`{by,title,at}` for a veto of the past ten minutes, so everyone sees it).

- POST /queue `{source_url,start_position?,idempotency_key}` adds a song. With fair turns on, a new
  song lands where fair turns put it (each person's nth song in round n, starting after whoever
  played last); songs already waiting do not move.
- PATCH /queue/{id} `{expected_version,before_item_id}`: anyone with `music.queue` moves any
  waiting song (ready or preparing, not the current one) before `before_item_id`, or to the end
  when it is null. 409 if the song or the target is no longer waiting.
- POST /queue/{id}/next `{expected_version}`: your own song becomes your next one (it takes the
  place of your first waiting song; everyone else's stay put): `result:"first_of_yours"`. An admin
  can use it on any song, which pins it to play right after the current one:
  `result:"pinned_next"`. Anyone else's song: 403.
- POST /queue/{id}/veto `{expected_version}`: one veto per person, back three hours after use.
  On someone else's playing song it skips it (`result:"skipped"`); on a waiting one it removes it
  (`result:"removed"`). Your own song: 409 (remove it instead). Veto not back yet: 409
  `{code:"VETO_RELOADING",available_at}`.
- POST /queue/shuffle-mine `{expected_version}` shuffles only your waiting songs.
- DELETE /queue/{id}?expected_version=N removes a waiting, failed or awaiting-approval song:
  its owner or an admin only.

## History

GET /history `?limit=1..100&offset=&by=<user id>&before=<cursor>` returns newest first:
`{items:[{id,source_url,title,played_at,plays,requester:{id,name,avatar},favorite,saved_id,...}],
next_offset,next_before}`. Pass `next_before` back as `before` to continue after the last row:
plays that arrive while someone scrolls neither repeat nor skip rows (`offset` is ignored with
`before`, and still works alone). `by` lists everything a person ever played.

The secret-free fetcher uses a maximum of two slow provider requests, plus short live
lease/status actions. At most one bounded live producer writes an owned UUID FIFO. The
player sees that FIFO only after validating its houseos-fetch-owned manifest and lease;
it never receives a provider URL. Closing the reader, explicit stop, provider failure,
45-second stall, byte limit or lease expiry terminates the producer. Provider URLs/PIDs
are absent from manifests and responses. A service restart does not reuse an old FIFO.

One metadata future and one preparation/observation future keep slow work separate from
priority playback controls. The final load rechecks the current item, resolution generation,
desired state, sleep deadline, actor/session and destination worker lease. Restart explicitly
pauses a surviving player and leaves interrupted preparation failed, without replaying it.

Tests cover: private named playlist/confirmation; three distinct voters and revoked-vote
authorization; actual synthetic WAV→FLAC through bwrap with stale-file rejection; actual
synthetic FIFO bytes with one-producer limit, explicit renewal and forced expiry; controls
remain responsive while both slow lanes are blocked; cancelled preparation cannot load
when its slow resolver returns. These tests do not prove a live YouTube/SoundCloud stream
or physical speaker audibility, and they start no live internet audio or physical playback;
check those once on your own speakers.
