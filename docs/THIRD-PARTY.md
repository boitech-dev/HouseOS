# Third-party components

HouseOS's original source is shared under LICENSE (MIT); theme art as below. The short version, with credits and names: [NOTICE.md](../NOTICE.md). Artwork source/provenance is in assets; controls remain independent frontend code. No provider media, poster database dump, commercial movie, music download or account subscription is redistributed.

**The git checkout** holds no third-party packages, only their pins and notices: Python names, versions and hashes in backend/uv.lock, dependencies/requirements.lock.txt (runtime only) and dependencies/bundled-linux-cp313.txt; their licences in dependencies/PYTHON-PACKAGES.json; frontend packages in frontend/package-lock.json (exact provenance and registry integrity hashes) with their licence notices consolidated in dependencies/NPM-LICENSES.txt. Docker downloads the pinned packages when it builds.

**An offline release archive** also carries them: dependencies/wheelhouse/ (the original wheels, with their package metadata, author/licence fields and licence files, except http-ece, built from its locked upstream source because no wheel was published) and dependencies/npm-cache/ (the frontend packages with their metadata and licences).

The compiled frontend includes React/ReactDOM (MIT), lucide-react (ISC), qrcode (MIT) and the Fontsource packages for Jacquard 12, Alegreya Sans and IBM Plex Mono (fonts under the SIL Open Font License 1.1), along with their dependencies. Prettier (MIT) is a development-only formatter. Build tools include Vite/TypeScript and their dependencies. yt-dlp and helper packages retain their own upstream terms. Platform programs (FFmpeg, mpv, MariaDB, tusd, Node, Python, bubblewrap, optional faster-whisper models, Jellyfin/CLIs) are separately installed; their licenses are not replaced by the HouseOS MIT grant.

Data fetched at run time on your server (one derived index ships, as noted):

- **Wikidata** (CC0 1.0 public domain dedication): the film and series index behind Watch's filters and collections. A copy ships in `backend/houseos/data/film-index.json.gz` (derived from Wikidata, CC0); it is refreshed weekly through Wikidata's public query service and QLever (University of Freiburg's public mirror). Wikimedia asks for a named, polite client; HouseOS sends one and pauses between queries.
- **anime-offline-database** by manami-project (the cedya77 build is used), under the Open Database License 1.0 (ODbL); individual contents under the Database Contents License 1.0. HouseOS downloads it daily and keeps a derived index on your server; if you redistribute that index, the ODbL applies to it.
- **MyAnimeList via Jikan** (unofficial, rate-limited API): anime details, rankings and members' recommendations.
- **Cinemeta** (Stremio's public catalogue): film and series search, posters.
- **radio-browser.info**: the community radio directory.
- **libretro-database** (No-Intro, Redump and FBNeo DATs and libretro's metadata; see its repository for terms) and **libretro-thumbnails** (box art, title screens and in-game pictures): what Games names and pictures, downloaded per console when first needed.
- **EmulatorJS** (GPL-3.0), pinned at 4.2.3 from its CDN, and its **emulator cores** (each under its own licence; some, such as snes9x, are non-commercial), plus **RetroArch cores** from the libretro buildbot for TV play: fetched by your house when a console is first played, never shipped with HouseOS. **Sunshine** (GPL-3.0) and **RetroArch** (GPL-3.0) are installed on native Linux hosts by `setup_games_host.py` from their official packages. HouseOS ships no game, BIOS or firmware.

Catalogs (including Deezer's public API, asked once per song for its genre and cover; off in Control Room → House), Reddit, image services, OpenRouter, debrid services, the stream add-on you add and other providers have their own availability, account and usage terms. Bundling an adapter does not grant content rights or transfer paid service access.

The optional standalone bgutil helper is included as corresponding source under vendor/, GPL-3.0-only, with its upstream license and pinned revision. It is not relicensed under the HouseOS MIT license.

## Themes and their art

Each bundled theme states its licence in `themes/<id>/theme.json`:

- **MIT** (like the code): Base, Canary, Legacy, Kinari, Pocket Hatchling and Shōwa Platform.
- **CC BY 4.0** (reuse with credit to the author named in its `theme.json`): Pure, Modular,
  The Vampire's Keep, Millennium Skin and Bathhouse After Hours.
- **Zabiwa**: the theme's data is MIT; its pictures are © Zabiwa, all rights reserved. They ship
  only as crops of the artist's paintings, for this theme in HouseOS; reusing them elsewhere needs
  the artist's permission.
- **Fonts** bundled in a theme (`themes/<id>/fonts/`) are under the SIL Open Font License 1.1,
  with the licence text beside each font.
