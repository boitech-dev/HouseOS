# Kinari · requests to the platform

Done upstream (thank you): the tour's `contact.html`, the deck's inner padding, the header
banner's wash (`part.header.banner-wash`, Kinari sets 0), the sign-in page in the tour.

Still open:

1. **Surfaces anchor only vertically.** `<part>.surface` pictures are always centred
   horizontally, so a mark meant for one corner of a cover picture moves with the width. Part:
   the slot's `anchor` taking the nine positions layers take. Meanwhile Kinari uses 9-slice.
2. **A radius for the status bar's pills.** Over a `status.backdrop` picture the house's name
   and the controls sit on pills of `radius.full`; Kinari's shapes are paper (2–6 px), so it
   would square them. Part: `part.status.radius` (default `{radius.full}`).
