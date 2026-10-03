# Recipient setup checklist

- [ ] Install: `./houseos.sh` (Linux) or docs/WINDOWS.md (Windows, WSL 2); keep the setup code.
- [ ] First admin account through `https://<server>:8443`; Control Room → Setup shows what is left.
- [ ] Nox: Control Room → AI (ChatGPT or Claude sign-in, OpenRouter/OpenAI/Anthropic key, or a
      self-hosted model such as Ollama).
- [ ] Music: plays on the computer's speakers by itself; phones (Speaker mode) and Cast devices
      too; test one song, a radio station, and the "Even out songs" setting (House).
- [ ] Films: a Stremio add-on link with the user's own debrid service (Control Room → Integrations →
      Stream add-on → Browse add-ons), then a TV (Find devices); test picture, sound, subtitles, seek, stop.
- [ ] Watch filters, rows and collections work at once (the film index ships with HouseOS).
- [ ] Voice (optional): works over HTTPS; `./houseos.sh gpu on` for an NVIDIA card.
- [ ] Home Assistant (optional): Smart home room and the TV remote.
- [ ] Backups: `./houseos.sh backup` (or Control Room → Recovery); copy them off the computer.
- [ ] Invite housemates; customize the house name, look and Nox as the user likes.
