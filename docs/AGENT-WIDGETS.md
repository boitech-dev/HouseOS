# Widgets for another assistant

Another assistant connected over MCP (see the README, *Your own assistant*) can also show the
house in its own widgets (now playing, the TV, the board) with the **same token**, without a
model in the middle. Three addresses under `/api/v1/agent/`; the token covers only the groups it
was given in *Control Room → Agents* (music, tv, board, home).

| Address | What |
|---|---|
| `GET /api/v1/agent/now?parts=music,tv,board,home` | One snapshot, JSON. Leave `parts` out for all the token may see. |
| `GET /api/v1/agent/stream?parts=…` | Server-Sent Events: `event: now` with the same snapshot at once, then each time it changes (a playing song at least every 15 s). Lasts about 10 minutes; EventSource reconnects by itself. |
| `POST /api/v1/agent/act` | A button: `{"tool": "music_control", "arguments": {"action": "skip"}}` → `{"ok": true, "result": {…}}`. Any of the token's MCP tools, same arguments. |

**Token.** `Authorization: Bearer hos_…`. A browser's EventSource can't send headers, so `now` and
`stream` also take `?access_token=hos_…`; prefer fetching from your server when you can (a query
string ends up in logs). Any site may call these (CORS, no cookies). Revoking the token in
Control Room → Agents ends open streams.

**Clocks.** Every time is UTC with a `Z`. `music.song.position` is the position at the snapshot's
`at`: while `state` is `playing`, the position now is `position + (now − at)`. A screen's
`position` is at its own `at`.

**Pictures** (`art`, `poster`) are public addresses (YouTube stills, catalogue posters): an `<img>`
shows them without the token. `null` when there's none.

## The snapshot

```json
{
  "at": "2026-11-02T20:58:59Z",
  "music": {
    "state": "playing",
    "song": {"id": "…", "title": "Lucid Dreams", "artist": "Juice WRLD", "art": "https://i.ytimg.com/…",
             "duration": 239.5, "position": 81.2, "live": null, "requested_by": "Sam", "url": "https://www.youtube.com/watch?v=…"},
    "volume": 35, "sleep_at": null, "repeat": "off", "plays_on": "computer",
    "next": [{"id": "…", "title": "…", "artist": "…", "art": "…", "duration": 201, "requested_by": "Auto play"}],
    "waiting": 7, "version": 812
  },
  "tv": {"screens": [
    {"device_id": "…", "name": "Living room TV", "state": "playing", "title": "Scavengers Reign",
     "episode": {"season": 1, "episode": 11, "title": "Scavengers Reign · S01E11"},
     "poster": "https://…", "position": 612.4, "at": "2026-11-02T20:58:57Z", "duration": 1610,
     "audio": "en", "subtitles": "fr", "sleep_at": null, "workflow_id": "…", "version": 42}
  ]},
  "board": {"date": "2026-11-02",
            "groceries": [{"id": "…", "kind": "groceries", "version": 1, "label": "Rice", "quantity": "", "purchased": false}],
            "tasks": […], "today": […]},
  "home": {"devices": […]}
}
```

`music.state` is `playing`, `paused` or `stopped`. A screen's `state` is `idle`, `starting`,
`playing`, `paused` or `failed` (only `device_id`, `name` and `state` when idle). While
`starting` it has `progress` (`{"step": "checking", "done": 1, "total": 3}` or
`{"step": "preparing", "percent": 40}`); `failed` (the last 10 minutes) has `error`, why.

## Feedback without a model

Every `cinema_play` answer has `status`: `playing`, `starting`, `working`, `needs_answer`,
`not_found` or `failed`, and a one-line `message`. While `working` or `starting` it also has
`progress` and `retry_after` (seconds): call it again with the same arguments then; it reports on
the film already under way, never launches it twice. The screen's state in the stream says the
rest (started, or failed and why), even after the call returned. A part the token can't see
is left out; a part that failed has `{"error": "…"}`.

## Buttons

Use the MCP tool names and arguments (`tools/list` describes them all):

| Button | `tool` | `arguments` |
|---|---|---|
| Play / pause / skip / back | `music_control` | `{"action": "play" \| "pause" \| "skip" \| "previous"}` |
| Volume | `music_control` | `{"action": "volume", "value": 35}` |
| Play a song | `music_play` | `{"query": "Lucid Dreams Juice WRLD"}` |
| Film pause / resume / stop | `cinema_control` | `{"workflow_id": "…", "version": 42, "action": "pause"}` |
| A light | `home_control` | `{"name": "living room lamp", "action": "turn_on"}` |
| Tick a grocery | `groceries_purchase` | `{"items": [{"id": "…", "version": 1}], "purchased": true}` |
| Add groceries | `board_add` | `{"kind": "grocery", "text": "Rice", "more": ["Eggs"]}` |

A button's tool must be in the token's set: *essential* tokens have `music_play`, `music_control`,
`cinema_play`, `cinema_control`, `home_control`, `board_add`, `groceries_purchase` and the rest of
that short list; switch a token to *all tools* in Control Room → Agents for the others.

Every call is recorded for the house's admins (*Control Room → Agents → Activity*: when, which
tool, a summary of what it asked without private text, how long, and why it failed).
