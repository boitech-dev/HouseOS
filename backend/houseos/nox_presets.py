"""Nox's starter presets. Everything code can answer is answered by code: the favourites
queue, the week ahead and the house tour never call a model. Only "help me find something
to watch" talks, because it needs a conversation. Each code preset is also a tool."""

from datetime import date

CODE_PRESETS = {"favorites", "week", "tour", "theme_questions"}

# Kept current by tests/test_house_features.py: every room of the app is named in both languages.
TOUR = {
    "fr": """*Nox déploie ses ailes et s'éclaircit la voix.* 🦇

Bienvenue dans la maison ! Je suis **Nox**, l'intendant. Je ne suis pas un simple chatbot : je fais pour toi le quotidien que font les boutons de l'app, et en mode mise en route, un admin peut me demander de changer les réglages de la maison, chaque changement confirmé sur une carte.

**⚡ En 30 secondes**
• 🏠 **Accueil** : qui est là, ce qui passe, la journée, la maison en chiffres.
• 🎶 **Écouter** : un jukebox commun où **chacun passe à son tour**.
• 🍿 **Regarder** : choisis un film, je prépare la meilleure version, tu confirmes, ça part sur la TV.
• 🎮 **Jeux** : tes propres jeux, dans le navigateur ou sur la TV avec une manette ; tes sauvegardes te suivent.
• 📋 **Maison** : mur, courses, tâches, agenda et messages.
• 🗄️ **Fichiers** : tes fichiers, ceux de la maison, la musique et les films gardés ici.
• 💡 **Maison connectée** : lumières, prises, volets et chauffage, si tu utilises Home Assistant.
• 🙋 **Moi** : ton profil, tes réglages et ta chambre, **Mon espace**.
• 🦇 **Et moi** : demande-moi n'importe quoi, à l'écrit ou au micro 🎙️.

C'est tout ce qu'il faut pour commencer. La suite est pour les curieux 👇

───────────────

**🎶 La musique, sans dispute**
Colle un lien YouTube ou SoundCloud (même un lien de mix : je prends juste le morceau), cherche un titre ou lance une radio. Chaque nouveau morceau prend son tour (un de chacun, à tour de rôle), pour que personne ne monopolise les enceintes ; ensuite, tout le monde peut monter ou descendre n'importe quel morceau, et chacun a **un veto** toutes les trois heures pour passer ou retirer un morceau des autres. Les morceaux mis en ligne trop bas sont un peu remontés, les trop forts un peu baissés, sans jamais toucher aux basses ni aux drops. Tu peux aussi mélanger tes titres, garder tes coups de cœur, créer des playlists ou en importer une entière. Chaque morceau écouté est gardé sur le disque de la maison : la fois suivante, il démarre tout de suite. Sur une radio, je te dis quel titre passe, et je peux te le retrouver. La musique joue sur les enceintes de la maison, sur un Chromecast, ou sur ton téléphone en **mode enceinte** : relié à une enceinte Bluetooth, il devient l'enceinte de la maison.

**🍿 Le cinéma, en un geste**
Cherche un film, une série ou un anime. Je compare les versions à ta place : le son ou des **sous-titres intégrés** dans tes langues, la **VO**, la meilleure qualité que ta TV accepte. Je vérifie les trois meilleures avant de te proposer la bonne. Rien ne se lance sans ta confirmation. Ensuite : pause, avance, reprise où tu t'étais arrêté, épisode suivant, minuterie de sommeil, liste à regarder partagée. Pour trouver quoi regarder : des **filtres** (années, genres, thèmes comme zombies ou casses, un réalisateur, un acteur, un studio, des récompenses), des **collections** qui changent chaque semaine et avec les saisons, et **« Dans la même veine »** sur chaque titre. Et **Regarder → Web** : colle (ou partage depuis ton téléphone) un lien YouTube, TikTok, Instagram ou un .mp4, il passe sur la TV sans pub.

**📋 La maison qui s'organise toute seule**
Un mot sur le mur, des courses cochées par celui qui les achète, des tâches répétées chaque semaine avec un ✓ pour les finir, un agenda commun où tes rendez-vous peuvent rester **privés**, et des messages entre colocs avec des fichiers joints, téléchargeables directement depuis la maison.

**🏆 La maison en chiffres**
Sur l'Accueil : morceaux joués, genres préférés, heures d’écoute, soirées ciné du mois, et les **titres de la maison** (Maître DJ, Oiseau de nuit, Héros des tâches…) qui changent de main chaque semaine. Je te dirai quand tu es tout près d'en décrocher un 👀

**🦇 Ce que je peux faire pour toi**
• *« Mets du jazz »*, *« Monte le son à 40 »*, *« Passe au suivant »*
• *« Ajoute du lait et des œufs aux courses »*, *« Crée une tâche pour Léa : sortir les poubelles demain »*
• *« Qu'est-ce qu'on fait cette semaine ? »*, *« Envoie à Max que le dîner est prêt »*
• *« Trouve-nous un film d'horreur pas trop long »* → je te propose 10 idées avec affiches
• *« Mets la TV sur HDMI 2 »*, *« Baisse la TV à 15 »*
• *« Éteins les lumières du salon »*, *« Mets le chauffage à 20° »* (avec Home Assistant)
• *« Retrouve mon PDF des impôts »*, *« Souviens-toi que je préfère la VO »*
Je te réponds dans ta langue (l'admin peut en ajouter), je comprends la voix, et je me souviens de ce que tu me demandes de retenir.

**🔒 Comment je travaille**
Tout ce qui peut être fait par du code est fait par du code : files d'attente, agenda, statistiques, rafraîchissements. Je ne réfléchis que quand ça vaut la peine, donc je reste rapide et peu coûteux. J'utilise exactement les mêmes actions que les boutons, avec les mêmes droits : je ne peux rien faire que tu ne pourrais pas faire. Je demande **toujours** avant d'allumer ou de changer la TV. Tes conversations, ton historique de films et tes fichiers restent à toi.

Alors, par quoi on commence ? ✨""",
    "en": """*Nox unfolds its wings and clears its throat.* 🦇

Welcome to the house! I'm **Nox**, the house manager. Not just a chatbot: I do the everyday things the app's buttons do, and in setup mode an admin can ask me to change the house's settings, each change confirmed on a card.

**⚡ In 30 seconds**
• 🏠 **Home**: who's around, what's playing, today, the house in numbers.
• 🎶 **Listen**: a shared jukebox where **everyone takes turns**.
• 🍿 **Watch**: pick a film, I prepare the best version, you confirm, it plays on the TV.
• 🎮 **Games**: your own games, in the browser or on the TV with a controller; your saves follow you.
• 📋 **House**: wall, groceries, tasks, calendar and messages.
• 🗄️ **Files**: your files, the house's, and the music and films kept here.
• 💡 **Smart home**: lights, plugs, blinds and heating, if you use Home Assistant.
• 🙋 **Me**: your profile, settings and your own room, **My Space**.
• 🦇 **And me**: ask me anything, typed or by voice 🎙️.

That's all you need to start. The rest is for the curious 👇

───────────────

**🎶 Music without arguments**
Paste a YouTube or SoundCloud link (even a mix link: I just take the song), search a title or start a radio. Every new song takes its turn (one from each person in rotation), so nobody hogs the speakers; after that anyone can move any song up or down, and everyone has **one veto** every three hours to skip or remove someone else's song. Songs uploaded too quiet are raised a little and very loud ones lowered a little, never touching the bass or the drops. You can also shuffle your picks, keep favourites, build playlists or import a whole one. Every song played is kept on the house disk, so next time it starts instantly. On a radio, I tell you which song is on, and I can find it for you. Music plays on the house speakers, on a Chromecast, or on your phone in **Speaker mode**: paired with a Bluetooth speaker, it becomes the house speaker.

**🍿 Cinema in one gesture**
Search a film, a series or an anime. I compare the versions for you: sound or **embedded subtitles** in your languages, **original audio**, the best quality your TV accepts. I check the top three before offering you the right one. Nothing starts without your confirmation. Then: pause, seek, resume where you stopped, next episode, sleep timer, a shared watchlist. To find something to watch: **filters** (years, genres, themes like zombies or heists, a director, an actor, a studio, awards), **collections** that change every week and with the seasons, and **More like this** on every title. And **Watch → Web**: paste (or share from your phone) a YouTube, TikTok, Instagram or .mp4 link and it plays on the TV, no ads.

**📋 A house that organizes itself**
A note on the wall, groceries ticked off by whoever buys them, weekly tasks with a ✓ to finish them, a shared calendar where your appointments can stay **private**, and messages between housemates with attached files, downloadable straight from the house.

**🏆 The house in numbers**
On Home: songs played, favourite genres, hours of music, this month’s film nights, and the **house titles** (Head DJ, Night owl, Task hero…) that change hands every week. I'll tell you when you're close to winning one 👀

**🦇 What I can do for you**
• *"Play some jazz"*, *"Volume to 40"*, *"Skip this one"*
• *"Add milk and eggs to the groceries"*, *"Make a task for Lea: take the bins out tomorrow"*
• *"What's on this week?"*, *"Tell Max dinner is ready"*
• *"Find us a horror film that isn't too long"* → I suggest 10 ideas with posters
• *"Switch the TV to HDMI 2"*, *"TV volume to 15"*
• *"Turn off the living-room lights"*, *"Set the heating to 20°"* (with Home Assistant)
• *"Find my tax PDF"*, *"Remember that I prefer original audio"*
I answer in your language (the admin can add more), I understand voice, and I remember what you ask me to remember.

**🔒 How I work**
Whatever code can do, code does: queues, calendar, stats, refreshes. I only think when it's worth it, so I stay fast and cheap. I use exactly the same actions as the buttons, with the same permissions: I can't do anything you couldn't do yourself. I **always** ask before turning on or switching the TV. Your conversations, film history and files stay yours.

So, where shall we start? ✨""",
}

DAYS = {
    "fr": ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"],
    "en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
}
WORDS = {
    "fr": {
        "today": "Aujourd'hui",
        "tomorrow": "Demain",
        "all_day": "toute la journée",
        "for_you": "pour toi",
        "private": "privé",
        "intro": "Voici ce qui arrive 🗓️",
        "nothing": "Rien de prévu cette semaine. Calme plat dans la maison 🌙",
        "later": "Plus loin, à garder en tête :",
        "tasks": "À faire :",
        "overdue": "en retard",
        "fav_done": "C'est parti pour {n} classiques de la maison 🎶",
        "fav_empty": "Pas encore assez d'historique pour vos classiques : écoutez quelques morceaux et je m'en souviendrai 🎧",
    },
    "en": {
        "today": "Today",
        "tomorrow": "Tomorrow",
        "all_day": "all day",
        "for_you": "for you",
        "private": "private",
        "intro": "Here's what's coming up 🗓️",
        "nothing": "Nothing planned this week. All quiet in the house 🌙",
        "later": "Further out, worth knowing:",
        "tasks": "To do:",
        "overdue": "overdue",
        "fav_done": "Here come {n} house classics 🎶",
        "fav_empty": "Not enough history for house classics yet: play a few songs and I'll remember them 🎧",
    },
}


def day_label(value: str, today: date, language: str) -> str:
    day, words = date.fromisoformat(value[:10]), WORDS[language]
    if day == today:
        return words["today"]
    if (day - today).days == 1:
        return words["tomorrow"]
    name = DAYS[language][day.weekday()]
    return f"{name.capitalize()} {day.day}" if language == "fr" else f"{name} {day.day}"


def event_line(item, language):
    words = WORDS[language]
    when = words["all_day"] if item["all_day"] else item["start"][11:16]
    tags = [words["for_you"]] * item["for_you"] + [words["private"]] * item["private"]
    where = f" · {item['location']}" if item.get("location") else ""
    return f"{when} — {item['title']}{where}" + (f" _({', '.join(tags)})_" if tags else "")


def week_text(digest: dict, language: str) -> str:
    words, today = WORDS[language], date.fromisoformat(digest["today"])
    if not digest["week"] and not digest["later"] and not digest["tasks"]:
        return words["nothing"]
    lines = [words["intro"], ""]
    if not digest["week"]:
        lines.append(words["nothing"])
    current = None
    for item in digest["week"]:
        label = day_label(item["start"], today, language)
        if label != current:
            lines.append(f"**{label}**")
            current = label
        lines.append("• " + event_line(item, language))
    if digest["later"]:
        lines += ["", words["later"]]
        lines += [
            f"• **{day_label(i['start'], today, language)}** {event_line(i, language)}"
            for i in digest["later"]
        ]
    if digest["tasks"]:
        lines += ["", words["tasks"]]
        for task in digest["tasks"]:
            due = (
                words["overdue"]
                if task["due_date"] < digest["today"]
                else day_label(task["due_date"], today, language)
            )
            lines.append(f"• {task['title']} — {due}" + (f" _({words['for_you']})_" * task["for_you"]))
    return "\n".join(lines)


def favorites_reply(result: dict, language: str):
    words = WORDS[language]
    if not result["count"]:
        return words["fav_empty"], []
    card = {
        "kind": "result",
        "label": "Queued house favourites",
        "domain": "music",
        "status": "accepted",
        "count": result["count"],
        "items": [{"title": item["title"], "detail": ""} for item in result["items"][:10]],
        "href": "/listen",
    }
    return words["fav_done"].format(n=result["count"]), [card]


# The theme studio's opening, written once: five short questions with examples to pick from, so
# the first answer gives Nox (the model) everything it needs to propose three directions.
THEME_QUESTIONS = {
    "en": """🎨 **Let's make your theme.** Five quick questions: one line each is plenty, skip any you like.

1. 🌍 **What should it feel like?** A place, a thing or an era: *a rainy café at night, a 70s train, grandma's kitchen, a comic book…*
2. 🌗 **Light, dark, or both?**
3. 📱 **Where do you use HouseOS most?** *Phone at night, a kitchen tablet, a big screen…*
4. 🖼️ **Pictures?** A photo or artwork of yours behind the pages, a few small drawings, or just colours and textures.
5. 🚫 **Anything you don't want?** *A colour, too cute, too dark, too busy…*

Then I'll show you **three directions** side by side. Nothing is saved until you choose. ✨""",
    "fr": """🎨 **Créons ton thème.** Cinq petites questions : une ligne suffit, passe celles que tu veux.

1. 🌍 **Quelle ambiance ?** Un lieu, un objet ou une époque : *un café sous la pluie, un train des années 70, la cuisine de mamie, une BD…*
2. 🌗 **Clair, sombre, ou les deux ?**
3. 📱 **Où utilises-tu le plus HouseOS ?** *Le téléphone le soir, une tablette dans la cuisine, un grand écran…*
4. 🖼️ **Des images ?** Une photo ou une œuvre à toi derrière les pages, quelques petits dessins, ou juste des couleurs et des textures.
5. 🚫 **Ce que tu ne veux pas ?** *Une couleur, trop mignon, trop sombre, trop chargé…*

Ensuite je te montre **trois directions** côte à côte. Rien n'est enregistré avant ton choix. ✨""",
}


def run(preset: str, actor, db, language: str):
    """Reply text and cards for a code preset."""
    if preset == "tour":
        return TOUR[language], []
    if preset == "theme_questions":
        return THEME_QUESTIONS[language], []
    if preset == "week":
        from .household import calendar_digest

        return week_text(calendar_digest(db, actor), language), []
    if preset == "favorites":
        from .auth import require_permission
        from .music import queue_favorites

        require_permission(actor, "music.queue")
        return favorites_reply(queue_favorites(db, actor), language)
    raise ValueError(preset)


WATCH_GUIDE = """Preset "help me find something to watch": chat briefly, then recommend.
- Ask at most two short, friendly questions in one message (mood or genre, who is watching, how long, film or series, any language wish), unless the request already says enough.
- Then call cinema_recommend once with exactly 10 varied titles that fit, each with a one-line reason tied to what the resident said. No spoilers anywhere.
- After the card, add one short line: tap a poster to open it in Watch, ready to confirm. Never launch anything yourself."""
