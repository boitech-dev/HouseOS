# Requests to the platform (Legacy / carved-night)

Done by the platform (thank you): layers over their place's picture, status layers, header
layers over banners, a padded skinned deck, contact.html allowed. Still open:

1. **Header layers that follow the banner's crop.** A banner is drawn `cover` (scale ≈ 1.006,
   centred) and a layer at a whole scale, centred: they agree within a pixel only near the middle,
   so the sconces, the portrait and the bedroom curtain sit between x 150 and 264 of 400. Wanted:
   a header layer fit that uses the banner's own box and scale.
2. **Home's hero shows the page through its words' side.** Without `part.page.gallery` the page's
   moon and clouds show behind the greeting. Meanwhile: gallery at 92 % canvas (it also grounds
   Listen's columns and poster rows, which reads well here).
3. **The header's title line still takes clicks across the whole width.** The words box no
   longer does, but its `h1` is a full-width block, so the top ~38 px of a header layer can't be
   poked (the portrait answers on its lower half, the curtain below the title). Wanted: the h1
   sized to its words (`width: fit-content`) or `pointer-events` on its text only.
4. **Deck layers sit inside the deck's padding horizontally** (the layer box is 16 px narrower
   each side than the deck), so a layer can't align with a frame corner. Meanwhile: the candle
   stands on the bottom rail, just inside the corner.
