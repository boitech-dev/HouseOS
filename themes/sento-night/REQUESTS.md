# Requests to the platform (sento-night)

Both requests below were fixed by the platform during this rework; the theme now uses them.

1. **Resolved: status-bar layers were laid out as a flex item.** `.shell__status > :not(.shell__sky)`
   made `.ds-layers` `position: relative`, so status layers landed above the bar. Now the noren's
   sway and the cat's walk are status layers.
2. **Resolved: layers sat under a place's own slot picture** (hero, page, status, header). Now they
   draw over it (`"under": true` puts one behind). The hero's steam and falling drop are layers.

No open requests.
