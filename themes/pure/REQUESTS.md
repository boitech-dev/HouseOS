# Pure: requests to the platform

Resolved (thank you): per-scheme pictures (also per room), deck padding for a skinned deck,
layers over their place's picture, `shots/` ignored by `check`, `color.bg.current` /
`color.fg.current` (Pure's current room and settings page are now solid blocks of light).

1. **Pixel pieces that follow the current block.** What: a sprite colour that becomes
   `fg.current` inside the current room's block. Why: the rail's room marks paint in the light, so
   on the solid block of light they would vanish; Pure gives every mark a one-pixel shadow in the
   ground's colour (unseen on the page, drawn on the block). It works, but a true inversion of the
   mark would be cleaner. Part: rail.
2. **A hero poke that can land on the picture.** What: a hero layer piece placed relative to the
   `home.hero.backdrop` picture (its crop), not the hero box. Why: the idea of touching the blade
   of sun to invert it for a beat needs the piece to line up with the blade at every size; Pure
   keeps one poke (the rail's foot) meanwhile. Part: hero.
3. **Pure in place of Base in the picker.** What: hide Base from the picker (it stays the root).
   Why: the direction says Pure replaces Base; a theme can't do that from its own folder, and
   `themes/base` must not be edited. Part: picker.
