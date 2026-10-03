"""Games: the consoles HouseOS knows, as data. `libretro` names the folders of the open
libretro database and thumbnails; `browser` is the EmulatorJS core (None: TV only), `tv` the
RetroArch core. Where both exist they are the same emulator, so an in-game save (.srm) made in
the browser continues on the TV and back. `bios`: files the person brings (never downloaded);
`needs_bios` when the game can't start without them."""

SYSTEMS = {
    "nes": dict(name="NES", libretro="Nintendo - Nintendo Entertainment System",
                ext={".nes", ".fds", ".unf"}, browser="fceumm", tv="fceumm", header=16,
                aliases={"nes", "famicom", "nintendo"}, bios=["disksys.rom"]),
    "snes": dict(name="Super Nintendo", libretro="Nintendo - Super Nintendo Entertainment System",
                 ext={".sfc", ".smc"}, browser="snes9x", tv="snes9x", header=512,
                 aliases={"snes", "sfc", "super nintendo", "super famicom"}),
    "n64": dict(name="Nintendo 64", libretro="Nintendo - Nintendo 64", ext={".z64", ".n64", ".v64"},
                browser="mupen64plus_next", tv="mupen64plus_next", aliases={"n64", "nintendo 64"}),
    "gb": dict(name="Game Boy", libretro="Nintendo - Game Boy", ext={".gb"}, browser="gambatte",
               tv="gambatte", aliases={"gb", "game boy", "gameboy"}),
    "gbc": dict(name="Game Boy Color", libretro="Nintendo - Game Boy Color", ext={".gbc"},
                browser="gambatte", tv="gambatte", aliases={"gbc", "game boy color", "gameboy color"}),
    "gba": dict(name="Game Boy Advance", libretro="Nintendo - Game Boy Advance", ext={".gba"},
                browser="mgba", tv="mgba", aliases={"gba", "game boy advance"}, bios=["gba_bios.bin"]),
    "nds": dict(name="Nintendo DS", libretro="Nintendo - Nintendo DS", ext={".nds"}, browser="melonds",
                tv="melonds", aliases={"nds", "ds", "nintendo ds"}),
    "vb": dict(name="Virtual Boy", libretro="Nintendo - Virtual Boy", ext={".vb"}, browser="beetle_vb",
               tv="mednafen_vb", aliases={"vb", "virtual boy"}),
    "gc": dict(name="GameCube", libretro="Nintendo - GameCube", ext={".rvz", ".gcz", ".ciso"},
               browser=None, tv="dolphin", aliases={"gc", "gcn", "gamecube", "ngc"}),
    "wii": dict(name="Wii", libretro="Nintendo - Wii", ext={".wbfs", ".wad"}, browser=None,
                tv="dolphin", aliases={"wii"}),
    "md": dict(name="Mega Drive", libretro="Sega - Mega Drive - Genesis", ext={".md", ".gen", ".smd"},
               browser="genesis_plus_gx", tv="genesis_plus_gx",
               aliases={"md", "genesis", "megadrive", "mega drive", "sega genesis"}),
    "sms": dict(name="Master System", libretro="Sega - Master System - Mark III", ext={".sms"},
                browser="genesis_plus_gx", tv="genesis_plus_gx", aliases={"sms", "master system"}),
    "gg": dict(name="Game Gear", libretro="Sega - Game Gear", ext={".gg"}, browser="genesis_plus_gx",
               tv="genesis_plus_gx", aliases={"gg", "game gear", "gamegear"}),
    "32x": dict(name="32X", libretro="Sega - 32X", ext={".32x"}, browser="picodrive", tv="picodrive",
                aliases={"32x", "sega 32x"}),
    "segacd": dict(name="Mega-CD", libretro="Sega - Mega-CD - Sega CD", ext=set(), disc=True,
                   browser="genesis_plus_gx", tv="genesis_plus_gx", needs_bios=True,
                   aliases={"segacd", "sega cd", "mega cd", "megacd"},
                   bios=["bios_CD_U.bin", "bios_CD_E.bin", "bios_CD_J.bin"]),
    "saturn": dict(name="Saturn", libretro="Sega - Saturn", ext=set(), disc=True, browser=None,
                   tv="mednafen_saturn", needs_bios=True, aliases={"saturn", "sega saturn"},
                   bios=["sega_101.bin", "mpr-17933.bin"]),
    "dc": dict(name="Dreamcast", libretro="Sega - Dreamcast", ext={".gdi", ".cdi"}, disc=True,
               browser=None, tv="flycast", aliases={"dc", "dreamcast"}, bios=["dc/dc_boot.bin"]),
    "psx": dict(name="PlayStation", libretro="Sony - PlayStation", ext={".pbp"}, disc=True,
                browser="pcsx_rearmed", tv="pcsx_rearmed",
                aliases={"psx", "ps1", "playstation", "playstation 1"}, bios=["scph5501.bin"]),
    "ps2": dict(name="PlayStation 2", libretro="Sony - PlayStation 2", ext=set(), disc=True,
                browser=None, tv="pcsx2", needs_bios=True, aliases={"ps2", "playstation 2"},
                bios=["pcsx2/bios/scph39001.bin"]),
    "psp": dict(name="PSP", libretro="Sony - PlayStation Portable", ext={".cso"}, disc=True,
                browser=None, tv="ppsspp", aliases={"psp", "playstation portable"}),
    "pce": dict(name="PC Engine", libretro="NEC - PC Engine - TurboGrafx 16", ext={".pce"},
                browser="mednafen_pce", tv="mednafen_pce",
                aliases={"pce", "pc engine", "turbografx", "turbografx 16", "tg16"}),
    "ngp": dict(name="Neo Geo Pocket", libretro="SNK - Neo Geo Pocket Color", ext={".ngp", ".ngc"},
                browser="mednafen_ngp", tv="mednafen_ngp", aliases={"ngp", "ngpc", "neo geo pocket"}),
    "ws": dict(name="WonderSwan", libretro="Bandai - WonderSwan Color", ext={".ws", ".wsc"},
               browser="mednafen_wswan", tv="mednafen_wswan", aliases={"ws", "wsc", "wonderswan"}),
    "a2600": dict(name="Atari 2600", libretro="Atari - 2600", ext={".a26"}, browser="stella2014",
                  tv="stella2014", aliases={"a2600", "atari 2600", "2600"}),
    "a7800": dict(name="Atari 7800", libretro="Atari - 7800", ext={".a78"}, browser="prosystem",
                  tv="prosystem", aliases={"a7800", "atari 7800", "7800"}),
    "lynx": dict(name="Lynx", libretro="Atari - Lynx", ext={".lnx"}, browser="handy", tv="handy",
                 aliases={"lynx", "atari lynx"}, needs_bios=True, bios=["lynxboot.img"]),
    "jaguar": dict(name="Jaguar", libretro="Atari - Jaguar", ext={".j64", ".jag"},
                   browser="virtualjaguar", tv="virtualjaguar", aliases={"jaguar", "atari jaguar"}),
    "coleco": dict(name="ColecoVision", libretro="Coleco - ColecoVision", ext={".col"},
                   browser="gearcoleco", tv="gearcoleco", aliases={"coleco", "colecovision"},
                   needs_bios=True, bios=["colecovision.rom"]),
    "arcade": dict(name="Arcade", libretro="FBNeo - Arcade Games", ext=set(), browser="fbneo",
                   tv="fbneo", aliases={"arcade", "fbneo", "mame", "neogeo", "neo geo", "cps1", "cps2"},
                   bios=["neogeo.zip"]),
}  # fmt: skip

# Files that say what they hold only through their folder (or what's inside them).
AMBIGUOUS = {".zip", ".7z", ".iso", ".bin", ".cue", ".chd", ".m3u", ".img"}
# The file a disc game is opened by; its tracks (.bin next to a .cue) aren't games of their own.
DISC_ENTRY = {".cue", ".chd", ".m3u", ".iso", ".gdi", ".cdi", ".pbp", ".cso", ".rvz", ".gcz", ".ciso"}
BY_EXT = {ext: key for key, s in SYSTEMS.items() for ext in s["ext"]}


def system_for(name, folders=()):
    """The console a file belongs to: its extension, else the nearest folder named after one."""
    import os

    ext = os.path.splitext(name)[1].lower()
    if ext in BY_EXT:
        return BY_EXT[ext]
    for folder in reversed(folders):
        label = folder.casefold().replace("_", " ").replace("-", " ").strip()
        for key, system in SYSTEMS.items():
            if label == key or label in system["aliases"] or label == system["name"].casefold():
                return key
    return None
