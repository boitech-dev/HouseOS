# Requests to the platform (Pocket Hatchling)

1. **The gallery ground paints over its own content in rounded corners.**
   Part: `part.page.gallery` (listen.css, watch.css, house.css, patterns.css:
   `outline: var(--space-3) solid var(--pv-gallery)` with `border-radius: var(--part-panel-radius)`).
   With a panel radius above ~10 px the outline's inner curve covers the first letters of
   headings that sit in the corner ("Up next", "Ideas" lost their first stroke at 18 px).
   Suggested: draw the gallery margin with `box-shadow: 0 0 0 var(--space-3) var(--pv-gallery)`
   (painted under the content) instead of `outline`.
   Meanwhile: cards use radius 10.

2. ~~Hero and status layers under the slot picture~~ and 3. ~~deck padding~~: done by the
   platform (thanks). The hero sky is `under`; the deck is now a 9-slice egg shell.

4. **French dock label.** The Ask door's "Demander à Nox" is wider than its fifth of a 390 px
   dock and touches "Regarder" (Base does the same). Caption weight lowered to 600 here.

5. **Status layers on phones.** The status bar's pills cover almost the whole bar on a phone
   (a 30 px gap between the name and the signs), so a status layer (Pip on the garland) is
   only glimpsed there. A way to keep a band above or below the pills clear, or a phone-only
   anchor, would let it show.
