# Cinema API

All under `/api/v1/cinema`; authenticated capability `cinema.use`; mutations CSRF.
Errors `detail:{code,message,stage,retryable}`. No raw media URLs, credentials or paths.

- `GET /search?q=…&kind=movie|series`: `{items:[{id,title,kind,year,canonical_id,layers}],errors:[{code,message,stage,retryable}]}`. Errors remain visible even if the other catalog succeeds.
- `GET /titles/{id}`: same title plus description/episodes, each episode `{id,title,season,episode}`.
- `GET /devices`: `{items:[{id,name,adapter,state,observed_at,capabilities,version}]}`.
- `POST /devices/{id}/inspect`: fresh destination status; no playback.
- `GET /preferences`; `PUT /preferences` body fields audio_language,subtitle_language,subtitles_on,quality,maximum_resolution,hdr,autoplay,preferred_device,source_selection. Returns saved defaults.
- `POST /discover` body `{media_id,device_id,season?,episode?,preferences?:{},idempotency_key}`. Returns workflow `{id,state,version,media_id,device_id,choice_set?,provisional:[],error?,confirmation_id?,preview?}`. Discovered unprobed sources explicitly provisional. Account-write confirmation separate from playback.
- `GET /workflows/{id}` returns own workflow, plan summary if present.
- `POST /workflows/{id}/validate` body `{version}` creates bounded debrid-preparation preview and confirmation (no account write yet).
- `POST /confirmations/{id}` empty body executes exact stored operation once; approval UI only, not an AI boolean. Returns workflow.
- `POST /workflows/{id}/select` body `{version,choice_set_id,choice}` where choice is source UUID, frozen ordinal or unique description. Returns preflight plan + playback confirmation, or recoverable error. No play until confirmation.
- `POST /workflows/{id}/control` body `{version,action:"pause"|"resume"|"stop"|"seek",position?:seconds}`. Returns sent/unverified until fresh observed status.
- `POST /workflows/{id}/observe` body `{version}` reads fresh adapter state, persists own checkpoint and reports per-dimension evidence.
- `POST /workflows/{id}/change` body `{version,device_id?,preferences?:{},source_choice?}` previews track/source/destination change preserving checkpoint; new confirmation required.
- `GET /state?filter=continue|watchlist|favorites|history|all`: `{items:[{media_id,title,position,duration,watched,favorite,watchlist,version,last_watched_at,...}]}`; own data only.
- `PUT /state/{media_id}` body `{watched?,favorite?,watchlist?,preferred_release?,version?}`.
- `DELETE /state/{media_id}/history`: resets own history/resume; retains favorite/watchlist/media files.
- `GET /health`: normalized integration setup/status, no secrets.
- Admin `POST /devices`: name,adapter(`jellyfin`, `cast` or `dlna`; `dlna` is a music-only speaker or TV),address (literal LAN IP),session_id,capabilities. `PUT /devices/{id}` same plus version. Technical profile configuration is not physical verification.

Workflow states include discovered,awaiting_preparation_confirmation,awaiting_choice,
awaiting_playback_confirmation,preparing,command_sent,playing_observed,paused,
stopped,recovery_required,failed. Source summaries in frozen choice_set.candidates:
`{id,rank,release,layer,size,height,hdr,video_codec,audio,subtitles,mode,warnings,evidence}`.
A choice_set has id,revision,expires_at. Up to five usable candidates; no padded results.

Empty/unconfigured Cinema is normal until integrations are connected; never seed demo
film posters/history or infer TV availability. “command_sent” is not “playing”.

## Browsing: explore, collections, "More like this"

These read local indexes only (`cinema_explore.py`): films and series from the weekly Wikidata film
index (`film_index.py`), anime from the anime offline database (`anime_offline.py`). No model is
involved and nothing waits on a remote catalogue. Returned titles are stored like search results,
so each has an openable `id` and a same-origin `poster`.

- `GET /explore?kind=movie|series|anime` with any of `q` (title, also French title and synonyms),
  `year_from`, `year_to` (1880–2100), `genre`, `tag` (comma-separated theme keys, up to four, all
  must match), `person` (director or cast; studio for anime), `award`, `max_minutes` (1–600),
  `max_episodes` (1–3000), `airing` (anime), `season=WINTER|SPRING|SUMMER|FALL` (anime),
  `sort=known|newest|oldest|rated` (default `known`), `offset`.
  Returns `{items,total,next_offset}`, 24 per page; `next_offset` is null at the end.
- `GET /explore/facets?kind=…`: what can be filtered right now, only choices with titles behind
  them: `{ready,genres,tags:[{key,label}],awards:[{key,label}],years:[min,max],people_label}`.
  HouseOS ships a ready film index, so `ready` is true from the first start.
- `GET /explore/people?kind=…&q=…` (2+ characters): up to 8 names, best known first.
- `GET /collections?kind=…`: the Watch home's rows, `{items:[{key,title,name,group,total,sort,
  query,filters}]}`: classic genre rows (`group:"classic"`), then this month's seasonal
  collections, the pinned ones and six more that rotate weekly (`group:"niche"`, the same for
  everyone that week). Each row loads its own titles, endless and sideways, with
  `GET /explore?kind=…&sort=…` plus its `query`; `filters` reopens it in the explore view. A row
  with fewer than six titles is left out.
- `GET /for-you?kind=…`: "Recommended for you", `{items,based_on}`: up to 24 titles most like the
  last five this person watched in that tab (films, series or anime), without those seen.
- `GET /titles/{id}/similar`: "More like this", `{items,franchise,source}`, up to 12 items. For
  anime, MyAnimeList members' recommendations through Jikan (`source:"myanimelist"`), then
  similar themes and studio, plus the same franchise; when MyAnimeList is unreachable, themes only
  (`source:"themes"`). For films and series, the same director, cast and themes from the film
  index. 404 for an unknown title.

## Web videos (`/api/v1/cinema/web`, `cinema_web.py`)

- `GET /cinema/web`: your last 30 links, newest first: `id, url, title, site, uploader, duration,
  height, state (queued | reading | downloading | ready | failed), progress (0–1 while downloading),
  error (a code), kept (the file is still here), device_id, needs_replace, workflow_id,
  workflow_state, poster, played_at`.
- `POST /cinema/web {text, device_id, replace?}`: `text` is the link or a whole shared message
  (the first address is taken, `https://` added). Returns the card, `queued`. `422
  WEB_VIDEO_LINK_INVALID` when there is no link; `404` for an unknown screen or a speaker.
- `POST /cinema/web/{id}/play {device_id, replace?}`: play again (downloaded again if deleted),
  or `replace: true` to replace what is on the screen.
- `DELETE /cinema/web/{id}`: forget it and its file; `409` while it is on a screen.
- Failure codes on a card: `WEB_VIDEO_PLAYLIST, WEB_VIDEO_LIVE, WEB_VIDEO_TOO_LONG (>4 h),
  WEB_VIDEO_TOO_BIG (>6 GB), WEB_VIDEO_NO_SPACE, WEB_VIDEO_DRM, WEB_VIDEO_UNSUPPORTED,
  WEB_VIDEO_SIGN_IN, WEB_VIDEO_NOT_FOUND, WEB_VIDEO_INTERRUPTED`, the YouTube ones shared with music,
  and the films' playback codes. All need `cinema.use`.

## TV remote (`/api/v1/tv`, `tv_remote.py`)

Allowed with `home.control` or `cinema.use` (admins always). One entry per remote; a screen can have
two.

- `GET /tv`: `{items:[{id,target,name,adapter,via?,capabilities,inputs,state}]}` for each
  enrolled Cast or DLNA screen (not speakers or speaker groups). `target:"tv"` is the TV itself
  through Home Assistant, present when its media player is mapped to that device
  (`adapter:"home_assistant"`, `via` names the device, `inputs` lists its sources).
  `target:"device"` is the Cast/DLNA device itself. `state` has `reachable`, and what the target
  reports (`on`, `input`, `volume`, `muted`, or the playing app/title).
- `POST /tv/{id}/remote` `{key,input?,target:"device"|"tv"}` (default `device`). `key` is one of
  `DPAD_UP`, `DPAD_DOWN`, `DPAD_LEFT`, `DPAD_RIGHT`, `DPAD_CENTER`, `BACK`, `HOME`, `VOLUME_UP`,
  `VOLUME_DOWN`, `VOLUME_MUTE`, `MEDIA_PLAY_PAUSE`, `POWER`, `INPUT` (with `input`, one of the TV's
  `inputs`; `tv` target only). Returns `{status:"sent",via,key}` where `via` is
  `home_assistant`, `remote` (Android TV Remote protocol, after pairing), `cast` or `dlna`. On the
  `device` target, arrows, OK, back, home and power need pairing (422 `TV_REMOTE_NOT_PAIRED`);
  without it Cast offers volume, mute and play/pause, DLNA volume only. A key the target lacks is
  422 `TV_KEY_UNSUPPORTED`; an unreachable TV is 422 `TV_UNREACHABLE`.
- `POST /tv/{id}/remote/pair`: the TV shows a six-character code (`{status:"code_shown"}`).
  `POST /tv/{id}/remote/pair/finish` `{code}` completes it (`{status:"paired"}`). Pairing is
  optional. The client identity stays on the server (`<runtime_root>/run/tv-remote`) and is never
  returned.

## Additional implemented endpoints

- `GET /cloud`: debrid account inventory, labels RD_CLOUD and local=false; never final URLs.
- `GET /titles/{id}/subtitles?language=fr&season=1&episode=2`: exact canonical-match OpenSubtitles results, owner-scoped opaque subtitle IDs, timing unverified.
- `POST /workflows/{id}/subtitle` `{version,subtitle_id}`: new bound preview; external download quota consumption occurs only after confirmation.
- `GET /titles/{id}/next?season=1&episode=2`: canonical next episode or end-of-series; no guessed filename progression.
- Request preferences can specify `allow_video_transcode:true` for explicit SDR <=1080p subtitle burn-in. This is never a permanent default. HDR burn-in is rejected rather than silently tone-mapped.

Worker hooks: `reconcile_playback(db)` (separate short periodic observer) and
`process_one_preparation(db)` (one dedicated preparation worker; potentially long).
Tables own foreign keys to users/media/workflow and are imported by the app migration.

The Cast conversion path currently uses a full bounded temporary spool before playback,
up to 80 GiB/source, with 2.2x space +20 GiB free-disk headroom and 1 concurrent preparation.
Direct compatible streams use an encrypted server-side upstream reference, pinned-DNS
HTTPS fetch, exact receiver-IP token route, byte ranges and no provider URL exposure.
Prepared conversion preserves video packets for audio-only changes, normalizes WebVTT,
and provides an explicitly confirmed SDR burn-in fallback. Source and preparation files
are transient data, not a claimed locally saved library item.

- `GET /workflows`: own 20 most-recent workflows for reload/resume controls.
- `POST /workflows/{id}/cancel` `{version}`: revoke an unplayed preview/preparation; active playback must use Stop. Downloader/process checks cancellation while preparing.
- `GET /devices/{id}/current`: permitted shared current-title/activity only, no another user's choices/history.
- `POST /workflows/{id}/co-watch` `{participate:true|false}`: opt only the caller into/out of private checkpoint updates. No initiator can assign another person's history.
- `POST /workflows/{id}/save-local` `{version}`: separate exact download confirmation/workflow. Requires files.shared.write, reserves Cinema quota (default 100 GiB), and atomically publishes only a size/probe/hash-verified file. No playback side effect.
- Title records include `poster` same-origin URL. Raster images are bounded, decoded and resized server-side; no remote SVG/HTML forwarding.

Diagnostics `/health` performs cached (30 s), bounded (3 s per subcheck) real restricted
Jellyfin library/session queries, local Comet manifest checks, debrid account checks when
authorized/configured, and the exact configured HA media-player state. Device observations
include freshness/age; stale is unknown. No physical control is part of a health query.

Slow discovery has a durable interface: `POST /operations/discover` with the same
Discover body returns `{status:"accepted",operation_id}`. Poll
`GET /operations/{id}` for accepted/running/completed/failed/unverified; completed
returns `{workflow_id,workflow}`. The owning actor and current session are checked
again when work starts. An interrupted running operation becomes unverified and is
never blindly retried. Source-validation confirmation atomically consumes its approval
and queues the exact at-most-five candidate batch, returning the preparing workflow
immediately. The dedicated Cinema worker handles this work separately from music.

TV control is intentionally separate from playback:
- `GET /devices/{id}/tv`: `{state,changed_at,observed_at,volume,input,inputs}` from the configured exact HA entity.
- `POST /devices/{id}/tv-prepare`: `{version,action:"power_on"|"power_off"|"volume"|"input",value?}`; volume is 0–75 percent. Returns `{confirmation_id,preview}` with current evidence/expiry.
- `POST /device-confirmations/{id}`: consume the actor-bound, revision-bound preview once. Returns observed/command_sent/command_outcome_unknown; unknown commands never repeat automatically.

`python -m houseos.cinema_observer` runs a separate five-second observation/checkpoint
cycle. Finished preparation scratch is removed only for terminal workflows after 24h,
without live relay grants; media-library/upload data is never part of this cleanup.
`python -m houseos.cinema_worker` serializes durable catalog/validation operations and
long preparation work. Worker interruption does not automatically replay physical commands.

Autoplay currently requires a positively observed Cast FINISHED event for the exact
current media, an already-selected ready debrid season pack containing the unique canonical
next episode, unchanged quality/HDR and a compatible non-costly direct route. It performs
no new debrid add/select, preserves request languages/subtitles, waits 15 seconds allowing
cancellation, and rechecks destination/authorization. Authorization is bounded to three
next episodes/two hours/current machine boot. Native Jellyfin synthetic progress is not
sufficient EOF evidence; its Next button remains the explicit supported route.

Jellyfin library items can also use the Cast route. HouseOS obtains exact MediaSourceId
bytes through the restricted runtime user's authenticated server connection; relay tokens
refer to encrypted item/source descriptors, never credential-bearing Jellyfin URLs. Native
Jellyfin remains available. Conversion/text subtitle extraction uses the same bounded spool
and video-preserving pipeline for both local-library and debrid sources.

Every direct/prepared/subtitle relay stream periodically rechecks grant, session, user,
workflow and destination ownership after at most 1 MiB or 1 second of active delivery. A
revoked stream stops and closes its upstream iterator. Local ranges/HEAD are preserved.

Jellyfin sidecars are retrieved from its authenticated exact item/source/subtitle endpoint
and normalized to WebVTT. Native-library indexes can shift when sidecars exist; the
preparation worker proves a unique mapping to actual file streams before conversion.
Ambiguity returns TRACK_MAPPING_AMBIGUOUS. Approved external text tracks support the
same explicit SDR burn fallback as embedded tracks. Codec profiles can specify
maximum_frame_rate and pixel_formats to constrain bit depth/chroma alongside codec
profile/level, resolution and HDR/Dolby Vision checks.
