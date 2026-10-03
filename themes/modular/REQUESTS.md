# Modular: requests to the platform

Done (thank you): status layers, `part.header.banner-wash`, per-scheme pictures, `color.bg/fg.current`, per-room-per-scheme pictures.

1. ~~Selected rows can't be inverted~~ **done** (`color.bg.current` / `color.fg.current`): the
   rail's current room and the settings menu's current page are now an ink block with paper
   words (paper with ink by night). The room marks carry a paper contour so they draw themselves
   in line on that block. Other selected rows (lists, pressed buttons) keep the ink tint.
2. ~~Per-room pictures can't also be per-scheme~~ **done** (`rooms: {room: {light, dark}}`):
   each room's banner now has a night file, the true negative (a paper emblem with ink cuts).
3. **The music cover's placeholder** paints `color.bg.raised` (shared with buttons, cards and
   onboarding), so a theme can't give an empty cover its own ink tile. Wanted: a
   `material.media.placeholder` colour.
