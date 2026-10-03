# Midnight House — writing rules

1. **French first.** Residents see French by default; the administrator sees English.
   Every user-facing string goes through `t("English source")` with a French entry in
   `frontend/src/locale_fr.ts`; `npm run build` fails on a missing translation. French
   says "tu" to everyone, everywhere, never "vous".
2. **Buttons are verbs** that say exactly what happens: "Lancer sur la TV", "Ajouter à
   la file", "Importer 137 morceaux". A success message repeats the verb in the past:
   "Ajouté à la file".
3. **Name things by what people see**, never by how the system works. Forbidden in the
   interface: probe, job, workflow, sink, HLS, spool, relay, provider, candidate,
   unverified, command_sent, version (of a release), destination. Use: source, screen
   ("écran"), speakers ("enceintes"), preparing ("préparation"), checking ("vérification").
   "Debrid · 4K" is allowed as a source label; never name the debrid provider itself.
4. **Honest states.** "Envoyé à la TV" until the TV confirms; then "En lecture".
   "C'est lancé" for background work; never "Terminé" before it is.
5. **Errors** say what happened and what to do next, without apology:
   "La TV ne répond pas. Vérifie qu'elle est allumée, puis réessaie."
6. **Lore lives around actions, not in them.** Headers, empty states, loading and success
   moments can speak as the house ("Le salon est silencieux. Ajoute le premier
   morceau."). Labels stay plain: "Musique", "Courses", "Fichiers".
7. **Short.** One sentence where one is enough. No "please", no "successfully", no
   exclamation marks except in a genuine celebration.
8. **Times and sizes** use Plex Mono: `1:13:36`, `4,2 Go`, `21:43`. French number and
   date formats in French.
9. **The familiar (Nox)** speaks briefly and warmly, in the language of the message it
   answers; it never pretends something happened.
