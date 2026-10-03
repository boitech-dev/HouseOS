// ==UserScript==
// @name         HouseOS: Show on the TV
// @namespace    houseos
// @version      1.0.0
// @description  A "Show on TV" button on YouTube: HouseOS turns the TV on and plays the video full screen there, from where you are in it.
// @match        https://www.youtube.com/*
// @match        https://m.youtube.com/*
// @grant        GM_xmlhttpRequest
// @grant        GM_getValue
// @grant        GM_setValue
// @grant        GM_registerMenuCommand
// @connect      *
// @run-at       document-idle
// @noframes
// ==/UserScript==

// Your HouseOS address and its screen key (Control Room → Devices → Show on the TV) are asked for
// on first use and kept in Tampermonkey's storage, never in this file. Shortcut: Alt+T.
(function () {
  "use strict";

  const settings = () => ({ address: GM_getValue("address", ""), key: GM_getValue("key", "") });

  function setUp() {
    const now = settings();
    const address = prompt("HouseOS address (for example https://houseos.local:8443):", now.address || "https://");
    if (!address) return false;
    const key = prompt("Screen key (HouseOS → Control Room → Devices → Show on the TV):", "");
    if (!key) return false;
    GM_setValue("address", address.trim().replace(/\/+$/, ""));
    GM_setValue("key", key.trim());
    return true;
  }

  // YouTube's pages refuse innerHTML (Trusted Types): everything is built node by node.
  let toast;
  function say(text, failed) {
    if (!toast) {
      toast = document.createElement("div");
      Object.assign(toast.style, {
        position: "fixed", bottom: "84px", right: "24px", zIndex: 2147483647, maxWidth: "340px",
        padding: "10px 14px", borderRadius: "10px", font: "14px/1.4 Roboto, Arial, sans-serif",
        color: "#fff", boxShadow: "0 4px 16px rgba(0,0,0,.4)", transition: "opacity .3s",
      });
      document.body.appendChild(toast);
    }
    toast.textContent = text;
    toast.style.background = failed ? "#b3261e" : "#202124";
    toast.style.opacity = "1";
    clearTimeout(say.timer);
    say.timer = setTimeout(() => (toast.style.opacity = "0"), failed ? 9000 : 5000);
  }

  const onVideo = () => /^\/(watch|shorts\/|live\/)/.test(location.pathname);

  function show() {
    if (!onVideo()) return say("Open a video first.", true);
    let { address, key } = settings();
    if ((!address || !key) && !setUp()) return;
    ({ address, key } = settings());
    const video = document.querySelector("video");
    const at = video && video.currentTime > 1 ? Math.floor(video.currentTime) : null;
    if (video) video.pause(); // it carries on, on the TV
    say("Sending to the TV…");
    GM_xmlhttpRequest({
      method: "POST",
      url: address + "/api/v1/tv/screen/show",
      headers: { "Content-Type": "application/json", Authorization: "Bearer " + key },
      data: JSON.stringify({ url: location.href, at }),
      timeout: 90000,
      anonymous: true, // the key, never your HouseOS sign-in
      onload(reply) {
        let body = {};
        try {
          body = JSON.parse(reply.responseText);
        } catch (e) {}
        if (reply.status === 200) {
          const tv = body.tv && body.tv.name ? body.tv.name + ": " + body.tv.done.join(", ") : "on the computer";
          return say("On its way to the TV (" + tv + ").");
        }
        const detail = body.detail || {};
        if (reply.status === 401) say("HouseOS refused the screen key. Set it again from Tampermonkey's menu.", true);
        else say(detail.message || (typeof detail === "string" ? detail : "HouseOS answered " + reply.status + "."), true);
      },
      onerror: () => say("HouseOS didn't answer at " + address + ".", true),
      ontimeout: () => say("HouseOS took too long to answer.", true),
    });
  }

  function button() {
    let node = document.getElementById("houseos-show-on-tv");
    if (!node) {
      node = document.createElement("button");
      node.id = "houseos-show-on-tv";
      node.type = "button";
      node.textContent = "📺 Show on TV";
      node.title = "Play this video on the TV, from here (Alt+T)";
      Object.assign(node.style, {
        position: "fixed", bottom: "24px", right: "24px", zIndex: 2147483647, padding: "10px 16px",
        border: "0", borderRadius: "20px", background: "#cc0000", color: "#fff", cursor: "pointer",
        font: "500 14px Roboto, Arial, sans-serif", boxShadow: "0 4px 16px rgba(0,0,0,.35)",
      });
      node.addEventListener("click", show);
      document.body.appendChild(node);
    }
    // Hidden off video pages and while YouTube itself is full screen.
    node.style.display = onVideo() && !document.fullscreenElement ? "block" : "none";
  }

  GM_registerMenuCommand("Show this video on the TV", show);
  GM_registerMenuCommand("Set HouseOS address and key", setUp);
  document.addEventListener("keydown", (event) => {
    if (event.altKey && !event.ctrlKey && !event.metaKey && event.code === "KeyT") {
      event.preventDefault();
      show();
    }
  });
  // YouTube changes pages without reloading.
  for (const name of ["yt-navigate-finish", "fullscreenchange", "popstate"]) document.addEventListener(name, button);
  button();
})();
