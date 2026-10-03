// My space: the resident's own room, set up with Nox, then a daily selection (news, Reddit, art)
// refreshed without AI, and their saved anime titles.
import { useState, type ReactNode } from "react";
import { api, date, items, useData, useUser, type Obj } from "./api";
import {
  Badge,
  Button,
  Cluster,
  Grid,
  Hint,
  Icon,
  List,
  ListRow,
  Notice,
  Page,
  PageHeader,
  Problem,
  Section,
  Slot,
  Stack,
  State,
  Surface,
  Text,
  Tile,
} from "./design";
import { Assistant } from "./ask";
import { useI18n } from "./i18n";
import "./personal_space.css";

const SECTION_TITLE: Record<string, string> = {
  news: "The gazette",
  reddit: "Letters from your communities",
  art: "The picture window",
};

const PROMPTS = [
  ["A little reading", "Help me choose my news interests and prepare 5 headlines a day.", "newspaper"],
  ["My communities", "Help me choose up to five subreddits for a daily selection of up to 20 posts.", "mail"],
  ["A daily mood board", "Help me choose anime illustration tags for 5 images a day.", "image"],
] as const; // prettier-ignore

/** A link that opens elsewhere, in a new tab. */
const Out = ({ href, children }: { href: string; children: ReactNode }) => (
  <a className="space-out" href={href} target="_blank" rel="noopener noreferrer">
    {children}
    <Icon name="forward" size="s" />
  </a>
);

export function PersonalSpace() {
  const { t } = useI18n();
  const user = useUser();
  const config = useData("/personal-space/config");
  const daily = useData(
    config.data?.configured ? "/personal-space/today?version=" + config.data.version : null,
    { interval: 30 * 60 * 1000 },
  );
  const [draft, setDraft] = useState("");
  const [customize, setCustomize] = useState(false);
  const [bookmarks, setBookmarks] = useState(false);
  const [error, setError] = useState("");
  const [pending, setPending] = useState("");
  const favorites = useData(bookmarks ? "/personal-space/favorites" : null);
  const configured = config.data?.configured;
  const chatting = config.data && (!config.data.setup_complete || customize);
  const changed = () => {
    void config.reload();
    void daily.reload();
  };
  const configuredThroughChat = () => {
    setCustomize(false);
    changed();
  };
  const french = daily.data?.news_language === "fr";
  return (
    <Page>
      <div className="space-top">
        <Slot id="space.room.scene" className="space-top__scene" seed={user?.id || ""} />
        <PageHeader
          room="space"
          title={t("My space")}
          lead={t(
            configured
              ? "A few things you chose, refreshed every 12 hours."
              : "Make this little corner yours. Tell me what you enjoy.",
          )}
          actions={
            configured && (
              <Cluster>
                <Button
                  variant="quiet"
                  icon="heart"
                  pressed={bookmarks}
                  onClick={() => setBookmarks(!bookmarks)}
                >
                  {t("Saved titles")}
                </Button>
                <Button
                  variant="quiet"
                  icon="message"
                  pressed={customize}
                  onClick={() => setCustomize(!customize)}
                >
                  {t("Customize")}
                </Button>
              </Cluster>
            )
          }
          hint={
            config.data &&
            !configured && (
              <Hint id="space-setup">
                {t(
                  "News: choose your interests. Reddit: up to 5 communities. Art: tell me the characters or tags you enjoy. Choose 5–20 items per section each day; mix them and change them whenever you like.",
                )}{" "}
                {t(
                  "For example: technology news in English, r/science, and peaceful landscapes — 10 items each.",
                )}
              </Hint>
            )
          }
        />
      </div>
      <Problem
        error={config.error || daily.error || error}
        onRetry={() => {
          setError("");
          changed();
        }}
      />
      {config.loading && !config.data && <State kind="loading" />}
      {config.data && !configured && !config.error && (
        <Section>
          {/* Each opening says what Nox will ask; a tap puts it in the chat below. */}
          <Grid min="14rem" space={3}>
            {PROMPTS.map(([label, prompt, icon]) => (
              <Tile
                key={label}
                icon={icon}
                title={t(label)}
                detail={t(prompt)}
                onOpen={() => setDraft(t(prompt))}
              />
            ))}
          </Grid>
          <Text as="p" style="body-s" tone="muted">
            {t("Nothing is selected yet. Choose only what you want; daily updates use no AI.")}
          </Text>
        </Section>
      )}
      {chatting && (
        <Stack space={3}>
          {config.data && !config.data.setup_complete && (
            <Text as="p" style="body-s" tone="muted">
              {t(
                "Your setup chat stays here, even after a refresh. When your space looks right, tell the assistant ‘looks good’ to finish.",
              )}
            </Text>
          )}
          {user?.role === "admin" && <SpaceModel />}
          <Assistant
            quick
            purpose="personal_space"
            initialThread={config.data?.conversation_id}
            initialDraft={draft}
            onAction={configuredThroughChat}
          />
        </Stack>
      )}
      {configured && (
        <>
          {daily.loading && !daily.data && (
            <State kind="loading" title={t("Preparing your daily selection…")} />
          )}
          {daily.data && (
            <Text as="p" style="body-s" tone="muted">
              {t("Updated")} ·{" "}
              {daily.data.selected_at
                ? date(daily.data.selected_at, { dateStyle: "medium", timeStyle: "short" })
                : daily.data.day}{" "}
              · {t("Every 12 hours")} · {t("Automatic, without AI")}
            </Text>
          )}
          {/* Art first, as a strip across the top; the reading side by side under it. */}
          <div className="space-board">
            {[...(daily.data?.sections || [])]
              .sort((a: Obj, b: Obj) => Number(b.kind === "art") - Number(a.kind === "art"))
              .map((section: Obj) => (
                <SpaceSection key={section.kind} section={section} french={french} />
              ))}
          </div>
          {!daily.loading && daily.data && !daily.data.sections?.length && (
            <State kind="empty" title={t("Your space is clear.")}>
              {t("Add a reading list, communities or illustrations whenever you like.")}
            </State>
          )}
          {bookmarks && (
            <Section title={t("Your saved anime titles")}>
              <Problem error={favorites.error} onRetry={() => void favorites.reload()} />
              {favorites.loading && !favorites.data && <State kind="loading" />}
              <List>
                {items(favorites.data).map((item) => (
                  <ListRow
                    key={item.id}
                    title={<Out href={item.url}>{item.title}</Out>}
                    detail={item.provider}
                    actions={
                      <Button
                        variant="quiet"
                        size="s"
                        icon="heart"
                        busy={pending === item.id}
                        aria-label={t("Remove saved title") + " " + item.title}
                        onClick={async () => {
                          setPending(item.id);
                          try {
                            await api("/personal-space/favorites/" + item.id, "DELETE");
                            await favorites.reload();
                          } catch (e) {
                            setError((e as Error).message);
                          } finally {
                            setPending("");
                          }
                        }}
                      >
                        {t("Remove")}
                      </Button>
                    }
                  />
                ))}
              </List>
              {!favorites.loading && favorites.data && !items(favorites.data).length && (
                <State kind="empty" title={t("Your saved titles will stay here.")} />
              )}
            </Section>
          )}
        </>
      )}
    </Page>
  );
}

const SHOWN = 6; // items per reading list before "Show all"

/** One of today's sections: art as a strip of pictures, the reading as a short list. */
function SpaceSection({ section, french }: { section: Obj; french: boolean }) {
  const { t } = useI18n();
  const [all, setAll] = useState(false);
  const list = items(section);
  const art = section.kind === "art";
  const body = (
    <Section
      title={t(SECTION_TITLE[section.kind] || "Today's reading")}
      actions={
        <Badge tone="neutral">
          {art
            ? "Safebooru / Danbooru"
            : section.kind === "reddit"
              ? "Reddit RSS"
              : french
                ? "Le Monde RSS"
                : "BBC RSS"}
        </Badge>
      }
    >
      {(section.sources || [])
        .filter((source: Obj) => source.status !== "ready")
        .map((source: Obj) => (
          <Notice key={source.key} tone="warning">
            {source.key}:{" "}
            {t(
              source.status === "empty"
                ? "No matching items today."
                : "Source unavailable. No replacement has been invented; retry after 30 minutes.",
            )}
          </Notice>
        ))}
      {art ? (
        <ul className="space-gallery">
          {list.map((item) => (
            <li key={item.id}>
              <a className="space-art" href={item.url} target="_blank" rel="noopener noreferrer">
                <img
                  className="space-art__picture"
                  src={item.poster}
                  alt={item.title}
                  loading="lazy"
                  decoding="async"
                  width="220"
                  height="220"
                />
                <Text style="caption" tone="muted">
                  {item.artist}
                </Text>
              </a>
            </li>
          ))}
        </ul>
      ) : (
        <>
          <List>
            {(all ? list : list.slice(0, SHOWN)).map((item) => (
              <ListRow
                key={item.id}
                title={<Out href={item.url}>{item.title}</Out>}
                detail={[item.provider, item.date].filter(Boolean).join(" · ")}
              />
            ))}
          </List>
          {list.length > SHOWN && (
            <Button variant="quiet" size="s" onClick={() => setAll(!all)}>
              {all ? t("Show less") : t("Show all ({n})").replace("{n}", String(list.length))}
            </Button>
          )}
        </>
      )}
      <Text as="p" style="caption" tone="muted">
        {t(
          art
            ? "General-rated community artwork. Artists retain their rights; source pages provide credits."
            : section.kind === "reddit"
              ? "Public daily top-post RSS, up to 20 posts. Availability depends on Reddit; no login is requested."
              : french
                ? "Headlines from your chosen interests, in French. Open the source to read; some articles require a publisher subscription."
                : "Headlines from your chosen interests. BBC articles are in English; open the source to read.",
        )}
      </Text>
    </Section>
  );
  // The headlines are a newspaper.
  return section.kind === "news" ? (
    <Surface material="paper" className="space-paper" data-kind={section.kind}>
      {body}
    </Surface>
  ) : (
    <div className="space-part" data-kind={section.kind}>
      {body}
    </div>
  );
}

/** For admins: which model sets up My space, and where to change it. */
function SpaceModel() {
  const { t } = useI18n();
  const assistants = useData("/admin/assistants");
  const row = items(assistants.data).find((a: Obj) => a.purpose === "personal_space");
  if (!row) return null;
  return (
    <Text as="p" style="body-s" tone="muted">
      {t("This setup uses {model}.").replace("{model}", row.model || t("the everyday model"))}{" "}
      <a href="/control?tab=ai#assistant-models">{t("Change the My space model")}</a>
    </Text>
  );
}
