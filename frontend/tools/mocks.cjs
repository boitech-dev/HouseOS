// The test app dressed for pictures (screens.cjs, themes/_kit/tour.cjs): a song and a film
// playing, a small smart home, and the theme and language chosen in this browser only (the test
// account's own preferences are never written).
const tv = { id: "media_player.oled_tv", name: "Living room TV", domain: "media_player", area: "Living room", state: "playing",
  attributes: { volume_pct: 40, source: "Netflix", app_name: "Netflix", source_list: ["HDMI 1", "Netflix", "YouTube"] },
  actions: ["turn_off", "play", "pause", "stop", "previous", "next", "volume", "mute", "unmute", "source", "key"] }; // prettier-ignore
const device = (domain, id, area, on, pct) => ({ id: domain + "." + id, name: id[0].toUpperCase() + id.slice(1).replace("_", " "),
  domain, area, state: on ? "on" : "off", attributes: pct === undefined ? {} : { brightness_pct: pct },
  actions: domain === "light" ? ["toggle", "turn_on", "turn_off", "brightness_pct"] : ["toggle", "turn_on", "turn_off"] }); // prettier-ignore
// A song and a film playing, and a small smart home, so every bar and room shows.
async function mocks(page, { theme = "", scheme = "", lang = "en", motion = "" } = {}) {
  await page.route("**/api/v1/music", (r) => r.fulfill({ json: {
    version: 5, current_id: "song", desired: "playing", plays_on: "computer",
    items: [{ id: "song", title: "Clair de Lune", uploader: "Claude Debussy", status: "playing", duration: 300, owner_id: "x" }],
    observation: { status: "observed", item_id: "song", idle: false, paused: false, position: 95, volume: 40 } } })); // prettier-ignore
  await page.route("**/api/v1/cinema/current", (r) => r.fulfill({ json: { current: {
    id: "film", title: "Spirited Away", version: 1, state: "playing_observed", checkpoint: { position: 1800 }, duration: 7500,
    can_seek: true, volume_supported: true, volume: 30 } } })); // prettier-ignore
  await page.route("**/api/v1/house-settings", async (r) => {
    const response = await r.fetch();
    const json = await response.json();
    const preferences = { ...json.preferences, language: lang, ...(theme ? { theme, scheme } : {}), ...(motion ? { motion } : {}) };
    await r.fulfill({ response, json: { ...json, home_assistant: true, preferences } });
  });
  await page.route("**/api/v1/home", (r) => r.fulfill({ json: { curated: true, favorites: ["light.kitchen"], areas: [
    { name: "Kitchen", entities: [device("light", "kitchen", "Kitchen", true, 70), device("switch", "coffee_maker", "Kitchen", false)] },
    { name: "Living room", entities: [tv, device("light", "reading_lamp", "Living room", true, 30), device("light", "ceiling", "Living room", false, 0)] },
    { name: "Office", entities: [device("switch", "desk", "Office", true), device("light", "desk_lamp", "Office", true, 90)] },
  ] } })); // prettier-ignore
}
module.exports = mocks;
