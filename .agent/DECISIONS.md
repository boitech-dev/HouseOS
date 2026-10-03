# Standing design decisions

- One modular app and established media engines; no competing playback authority.
- Direct controls and assistants use the same permission-checked domain operations.
- Private history/memory/files are actor-scoped; admin usage visibility is not private-chat access.
- Routine automation is code, not repeated paid model calls; free, open data sources first.
- Preserve exact source/audio/subtitle/destination intent and truthful observed status.
- Retained music/local library and temporary Cinema streaming are different storage lifecycles.
- The shared queue: fair turns place new songs; anyone may then move any waiting song; one veto
  per person every three hours. Music levels are one fixed gain per song, never within a song.
- Served on the home network (HTTPS on :8443); away from home through Tailscale or the user's own
  reverse proxy (docs/DOCKER.md).
- Specifications are design context; actual recipient hardware acceptance remains separate.
