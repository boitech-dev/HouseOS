// What a machine code means to a person. Codes come from the server (errors, job states,
// probes); nothing in the interface shows one raw. Unknown codes read as a plain sentence.
import { t } from "./i18n";

const CODES: Record<string, () => string> = {
  FETCH_SANDBOX_NOT_VERIFIED: () =>
    t("Music sources are off on this server: start the fetch service in Control Room → Services."),
  FETCH_UNAVAILABLE: () =>
    t("The music source service isn't answering. Check Control Room → Services."),
  AUDIO_BRIDGE_UNAVAILABLE: () =>
    t("The speaker service isn't running. Check Control Room → Services."),
  PHYSICAL_OUTPUT_NOT_ENABLED: () =>
    t("No speaker is ready. Choose where music plays in Control Room → Speakers."),
  DEFAULT_SINK_UNAVAILABLE: () =>
    t("This computer's speakers aren't available right now; music is paused."),
  SELECTED_SINK_DISAPPEARED: () => t("The chosen speakers disappeared; music is paused."),
  LIVE_OUTPUT_SWITCH: () =>
    t("A live radio can only move between this computer's speakers. Stop it, then choose."),
  OUTPUT_CHANGED: () => t("The speakers changed meanwhile. Try again."),
  AUDIO_FILE_MISSING: () => t("This song's file is missing. Add it again."),
  AUDIO_COMMAND_FAILED: () => t("The speakers didn't accept that command. Try again."),
  SERVICE_BROKER_UNAVAILABLE: () => t("Service control isn't available on this install."),
  SOURCE_UNAVAILABLE: () => t("Can't be read right now. Try again, or another version."),
  SOURCE_REMOVED: () => t("This video was removed or made private."),
  PLAYLIST_NOT_FOUND: () =>
    t(
      "Private or missing playlist. Set it to Public or Unlisted on YouTube, or check the whole link was copied.",
    ),
  SOURCE_REGION_BLOCKED: () => t("Blocked in this country. Try another version of the song."),
  SOURCE_TIMEOUT: () => t("The source took too long to answer. Try again."),
  SOURCE_BUSY: () => t("The source is busy. Try again in a moment."),
  YOUTUBE_SIGN_IN_REQUIRED: () =>
    t("YouTube is blocking this server for now (a bot check). Songs already at home still play."),
  YOUTUBE_RATE_LIMITED: () =>
    t("YouTube is slowing this server down for a while. Songs already at home still play."),
  YOUTUBE_AGE_RESTRICTED: () =>
    t("Age-restricted: YouTube plays it only to signed-in adults. Try another version."),
  TRACK_TOO_LONG: () => t("Tracks longer than four hours can't play here."),
  QUEUE_FULL: () => t("The queue is full. Wait for a few songs to play."),
  STALE_QUEUE: () => t("The queue changed meanwhile. Try again."),
  QUEUE_CHANGED: () => t("The queue changed meanwhile. Try again."),
  ACCOUNT_ACTION_UNCERTAIN: () =>
    t("The debrid service didn't confirm that action. Check your debrid account, then try again."),
  DEBRID_REQUEST_REJECTED: () => t("The debrid service refused this request. Try another version."),
  EPISODE_AMBIGUOUS: () =>
    t("This pack doesn't say clearly which file is that episode. Try another version."),
  DEBRID_COUNTER_UNAVAILABLE: () =>
    t("The debrid service is busy right now. Try again in a minute."),
  AUTO_NOTHING_KEPT: () => t("No kept song matches these genres yet."),
  VETO_RELOADING: () => t("You've used your veto; it comes back three hours later."),
  PLAYBACK_INTERRUPTED: () => t("The song stopped before its end. Add it again to retry."),
  LIVE_SEEK_UNSUPPORTED: () => t("You can't seek in live radio."),
  RADIO_STATION_UNAVAILABLE: () => t("This station isn't broadcasting right now."),
  RADIO_DIRECTORY_UNAVAILABLE: () => t("The radio directory isn't answering. Try again soon."),
  VOICE_UNAVAILABLE: () => t("Voice isn't available right now; type instead."),
  VOICE_TRANSCRIPTION_FAILED: () => t("That recording couldn't be understood. Try again."),
  CODEX_UNAVAILABLE: () => t("The ChatGPT sign-in service isn't running on this install."),
  CODEX_SIGN_IN_REQUIRED: () => t("Sign in to ChatGPT again in Control Room → AI."),
  CLAUDE_SIGN_IN_REQUIRED: () => t("Sign in to Claude again in Control Room → AI."),
  PROVIDER_UNAVAILABLE: () => t("The AI service isn't answering. Try again soon."),
  PROVIDER_UNCONFIGURED: () => t("Nox isn't connected to an AI yet (Control Room → AI)."),
  PROVIDER_RATE_LIMIT: () => t("The AI service is limiting requests. Try again in a minute."),
  PROVIDER_TIMEOUT: () => t("The AI took too long to answer. Try again."),
  JELLYFIN_UNAVAILABLE: () => t("Jellyfin isn't answering. Check its address in Control Room."),
  JELLYFIN_UNCONFIGURED: () => t("Jellyfin isn't set up yet."),
  DEBRID_UNCONFIGURED: () =>
    t("The debrid service isn't set up yet (Control Room → Integrations)."),
  DEBRID_AUTH_EXPIRED: () => t("The debrid API token expired. Paste a new one in Control Room."),
  RELAY_UNCONFIGURED: () => t("The TV can't reach HouseOS yet. Check Control Room → Services."),
  TARGET_OFFLINE: () => t("That device is offline."),
  STORAGE_UNAVAILABLE: () => t("Storage isn't available. Check Control Room → Storage."),
  STORAGE_SPACE_LOW: () => t("Storage is almost full."),
  UPLOAD_TRANSPORT_UNAVAILABLE: () =>
    t("The upload service isn't running. Check Control Room → Services."),
  HOUSEOS_SHUTTING_DOWN: () => t("HouseOS is shutting down."),
  UNEXPECTED_FAILURE: () => t("Something went wrong. Try again."),
  // Watch → Web: a pasted video link (cinema_web.py, fetcher_web.py).
  GAMES_LIST_OFF: () =>
    t("This house doesn't download from the internet, so the game list and covers can't come in."),
  GAME_DUPLICATE: () => t("This game is already in the house."),
  GAME_FILE_UNSUPPORTED: () => t("That isn't a game file HouseOS knows."),
  GAME_FILE_MISSING: () => t("This game's file is gone."),
  GAME_LINK_INVALID: () => t("Paste a full https:// link to the game file."),
  GAME_LINK_UNAVAILABLE: () =>
    t("The site didn't hand over the file (down, private or removed). Try later, or upload it."),
  GAME_LINK_UNSAFE: () => t("That link doesn't lead to a public https:// address."),
  GAME_LINK_TOO_BIG: () => t("Bigger than 16 GB: too big to download from a link."),
  GAME_LINK_TIMEOUT: () => t("The site took too long to send the file. Try again later."),
  GAME_LINK_PAGE: () =>
    t(
      "That link opens a web page, not the game file. Paste the file's own link (it ends in .zip, .iso…).",
    ),
  GAME_LINK_INTERRUPTED: () => t("HouseOS restarted during the download. Add the link again."),
  GAME_NO_SPACE: () => t("The house's disk is too full for this game."),
  GAME_PATCH_INVALID: () => t("That isn't an .ips or .bps patch."),
  GAME_PATCH_OTHER_VERSION: () =>
    t("This patch is made for another version of the game (another region or revision)."),
  GAME_PATCH_TOO_BIG: () => t("Patches work on cartridge games, not discs."),
  GAMES_TV_NOT_SET_UP: () => t("TV play isn't set up on this house yet (Games → Set up)."),
  GAMES_TV_UNAVAILABLE: () => t("The TV streaming service isn't answering."),
  GAMES_TV_UNSUPPORTED: () => t("This console can't play on the TV."),
  GAMES_CORE_UNAVAILABLE: () => t("The emulator for this console didn't download. Try again."),
  GAMES_PAIR_FAILED: () => t("That code didn't work. Check the 4 digits on the TV."),
  WEB_VIDEO_LINK_INVALID: () => t("That doesn't look like a link. Paste the video's address."),
  WEB_VIDEO_PLAYLIST: () => t("That's a playlist. Paste the link of one video."),
  WEB_VIDEO_LIVE: () => t("Live streams can't play here yet."),
  WEB_VIDEO_TOO_LONG: () => t("Longer than 4 hours: too long to download."),
  WEB_VIDEO_TOO_BIG: () => t("Bigger than 6 GB: too big to download."),
  WEB_VIDEO_NO_SPACE: () => t("Not enough free space on the house disk for this video."),
  WEB_VIDEO_DRM: () => t("Copy-protected (like Netflix): it can't play here."),
  WEB_VIDEO_UNSUPPORTED: () => t("No video found at this link."),
  WEB_VIDEO_SIGN_IN: () => t("This site shows it only to signed-in people."),
  WEB_VIDEO_NOT_FOUND: () => t("Nothing at this link: removed, or a typo?"),
  WEB_VIDEO_INTERRUPTED: () => t("HouseOS restarted during the download. Play it again."),
  SOURCE_URL_EXPIRED: () => t("The site refused the download. Try again in a moment."),
  PERMISSION_REVOKED: () => t("Your sign-in changed meanwhile. Try again."),
  MEDIA_UNAVAILABLE: () => t("The file is gone from the house. Play it again."),
  HOME_UNCONFIGURED: () =>
    t(
      "Home Assistant isn't connected. An administrator can connect it in Control Room → Integrations.",
    ),
  HOME_TOKEN_REFUSED: () =>
    t("Home Assistant refused HouseOS's token. An administrator needs to create a new one."),
  HOME_UNREACHABLE: () =>
    t("Home Assistant didn't answer or refused the request. Try again in a moment."),
  HOME_NOT_EXPOSED: () => t("HouseOS isn't allowed to control this device."),
  HOME_UNAVAILABLE: () => t("Home Assistant reports this device unavailable."),
  PLAYBACK_START_FAILED: () => t("The screen did not accept the film."),
  AUDIO_CACHE_FULL: () =>
    t("No room left for more songs on the house disk. Free some space, then try again."),
  VOLUME_SUPERSEDED: () => t("A newer volume change replaced this one."),
  ACCOUNT_DELETED: () => t("Cancelled: the account that asked for it was deleted."),
};

export const knownCode = (code: string) => code in CODES;

/** A person-readable sentence for a code or status; plain words pass through translated. */
export function message(value: unknown): string {
  const text = String(value ?? "");
  if (CODES[text]) return CODES[text]();
  if (/^[A-Z][A-Z0-9_]{3,}$/.test(text)) {
    const words = text.toLowerCase().replaceAll("_", " ");
    return t(words[0].toUpperCase() + words.slice(1));
  }
  return t(text.replaceAll("_", " "));
}
