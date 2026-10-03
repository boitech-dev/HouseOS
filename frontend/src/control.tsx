// The Control Room (admins): the house's status, people, devices, AI and connections, storage and
// the house itself, as a list of places beside the chosen one (SettingsLayout).
import { t, getLanguage } from "./i18n";
import { useState, useEffect, useId } from "react";
import { AI_PROVIDERS, AiConnections } from "./providers";
import { ShutdownHouseOS } from "./shutdown";
import {
  SetupAdmin,
  AccessAdmin,
  STATE,
  stepTitle,
  type Step,
  ADDON_FIELD,
  BrowseAddons,
} from "./setup";
import { HouseActions } from "./house_actions";
import { ChangesAdmin } from "./changes";
import { HouseSettingsAdmin } from "./house_settings";
import { StorageAdmin } from "./files";
import { PairDialog, steersScreen } from "./tvremote";
import { Usage, ThemePicker, SchemeChoice, MadeHere, Studio } from "./me";
import { StartTheme, ThemePreview } from "./theme_preview";
import { qrColours, allThemes, renamed, useTheme } from "./design/theme";
import { api, useData, usePages, items, pretty, time, bytes, date, type Obj } from "./api";
import { message } from "./messages";
import { CONTROL_GROUPS, go } from "./nav";
import {
  Badge,
  Button,
  Checkbox,
  Chip,
  Cluster,
  ChipGroup,
  ConfirmSheet,
  Disclosure,
  Field,
  Form,
  Icon,
  type IconName,
  Input,
  LinkButton,
  List,
  ListHeading,
  ListRow,
  MoreBelow,
  Notice,
  Page,
  PageHeader,
  Problem,
  ReviewDetails,
  SearchInput,
  SecretInput,
  Section,
  Segmented,
  Select,
  type SettingsGroup,
  SettingsLayout,
  Sheet,
  Stack,
  State,
  Status,
  Surface,
  Text,
  Textarea,
  Tile,
  toast,
  type Tone,
} from "./design";
import "./me.css";

const GOOD = new Set([
  "ok",
  "healthy",
  "connected",
  "configured",
  "running",
  "completed",
  "confirmed",
]);
const BAD = new Set(["failed", "error", "down", "blocked"]);
const toneOf = (status: string): Tone =>
  GOOD.has(status) ? "success" : BAD.has(status) ? "danger" : "warning";

export function Admin() {
  const [tab, setTab] = useState(() => new URLSearchParams(location.search).get("tab") || "");
  const open = (key: string) => {
    setTab(key);
    history.replaceState(null, "", key ? "/control?tab=" + key : "/control");
    scrollTo({ top: 0 });
  };
  const groups: SettingsGroup[] = CONTROL_GROUPS.map(([label, places]) => ({
    label: t(label),
    items: places.map(([id, icon, name]) => ({ id, icon, label: t(name) })),
  }));
  return (
    <Page>
      <PageHeader room="control" title={t("Control Room")} />
      <SettingsLayout
        label={t("Control Room sections")}
        groups={groups}
        value={tab}
        onChange={open}
        overview={<Overview onOpen={open} />}
        mapped
      >
        {tab === "health" && <Health onOpen={open} />}
        {tab === "setup" && <SetupAdmin open={open} />}
        {tab === "access" && <AccessAdmin />}
        {tab === "house" && <HouseSettingsAdmin />}
        {tab === "themes" && <ThemesAdmin />}
        {tab === "services" && <ServiceAdmin />}
        {tab === "changes" && <ChangesAdmin />}
        {tab === "speakers" && <AudioAdmin />}
        {tab === "recovery" && <RecoveryAdmin />}
        {tab === "jobs" && <JobsAdmin />}
        {tab === "devices" && <DeviceAdmin />}
        {tab === "storage" && <StorageAdmin />}
        {tab === "users" && <Users />}
        {tab === "invites" && <Invites />}
        {tab === "ai" && <AiConnections />}
        {tab === "integrations" && <Integrations />}
        {tab === "usage" && <Usage />}
        {tab === "logs" && <ActivityLog />}
      </SettingsLayout>
    </Page>
  );
}

/** The Control Room's first view: how the house is, and what needs you. */
function Overview({ onOpen }: { onOpen: (place: string) => void }) {
  const health = useData("/admin/health");
  const setup = useData<Obj>("/admin/setup");
  const services = useData("/admin/services");
  const jobs = useData("/admin/jobs?state=active");
  const checks: Obj[] = health.data?.checks || [];
  const bad = checks.filter((c) => BAD.has(c.status)).length;
  const check = checks.filter((c) => !GOOD.has(c.status) && !BAD.has(c.status)).length;
  const down = items(services.data).filter((s) => serviceState(s).tone === "bad").length;
  const problems = useData("/admin/activity?needs=true");
  const duplicates = useData<Obj>("/files/library/duplicates");
  const doubles = Number(duplicates.data?.count || 0);
  // What to do next: setup steps left, then checks that aren't green (red first).
  const steps: Step[] = (setup.data?.steps || []).filter(
    (step: Step) => step.state === "todo" || step.state === "unavailable",
  );
  const issues = checks
    .filter((c) => !GOOD.has(c.status))
    .sort((a, b) => Number(BAD.has(b.status)) - Number(BAD.has(a.status)));
  const recent = items(problems.data).slice(0, 5);
  return (
    <div className="ds-settings__overview me-stack">
      <Problem error={health.error} onRetry={health.reload} />
      <div className="control-tiles">
        {setup.data && setup.data.done < setup.data.needed && (
          <Tile
            icon="wrench"
            title={t("Setup")}
            value={setup.data.done + " / " + setup.data.needed}
            detail={t("essentials ready")}
            onOpen={() => onOpen("setup")}
          />
        )}
        <Tile
          icon="shield-check"
          title={t("Health")}
          value={
            !health.data ? "…" : bad ? t("{n} problems").replace("{n}", String(bad)) : t("All good")
          }
          detail={check ? t("{n} to check").replace("{n}", String(check)) : undefined}
          onOpen={() => onOpen("health")}
        />
        <Tile
          icon="settings"
          title={t("Services")}
          value={
            !services.data
              ? "…"
              : down
                ? t("{n} need attention").replace("{n}", String(down))
                : t("All running")
          }
          onOpen={() => onOpen("services")}
        />
        <Tile
          icon="clock"
          title={t("Background work")}
          value={jobs.data ? String(items(jobs.data).length) : "…"}
          detail={t("waiting or running")}
          onOpen={() => onOpen("jobs")}
        />
      </div>
      {/* Every place, by group, with what you set there: the way in on a phone too,
          and above what needs you so every place is in sight first. */}
      <Section title={t("Everything in the Control Room")}>
        <div className="control-map">
          {CONTROL_GROUPS.map(([label, places]) => (
            <Surface key={label} material="raised" className="control-map__group">
              <Text as="h3" style="title-s">
                {t(label)}
              </Text>
              <List label={t(label)}>
                {places.map(([id, icon, name, what]) => (
                  <ListRow
                    key={id}
                    leading={<Icon name={icon} />}
                    title={t(name)}
                    detail={t(what)}
                    onOpen={() => onOpen(id)}
                  />
                ))}
              </List>
            </Surface>
          ))}
        </div>
      </Section>
      <div className="control-attention">
        <Section title={t("What needs you")}>
          {setup.data && health.data && !steps.length && !issues.length && !doubles ? (
            <State kind="empty" title={t("Nothing needs you right now.")} />
          ) : (
            <List label={t("What needs you")}>
              {steps.slice(0, 3).map((step) => (
                <ListRow
                  key={"setup-" + step.key}
                  leading={<Icon name="wrench" />}
                  title={stepTitle(step.key)}
                  detail={t("Setup")}
                  status={{ tone: STATE[step.state].tone, text: STATE[step.state].word() }}
                  onOpen={() => onOpen(step.tab)}
                />
              ))}
              {doubles > 0 && (
                <ListRow
                  leading={<Icon name="music" />}
                  title={t("Possible duplicate songs ({n})").replace("{n}", String(doubles))}
                  detail={t(
                    "The same song kept twice: pick the one to keep in Files → House music.",
                  )}
                  onOpen={() => go("/files?scope=music")}
                />
              )}
              {issues.slice(0, 5).map((c) => (
                <ListRow
                  key={"check-" + c.component}
                  leading={<Icon name="shield-check" />}
                  title={pretty(c.component)}
                  detail={t(c.evidence || "Connection has not been verified.")}
                  status={{ tone: toneOf(c.status), text: t(pretty(c.status)) }}
                  onOpen={() => onOpen(c.tab || "services")}
                />
              ))}
            </List>
          )}
        </Section>
        <Section
          title={t("Recent problems")}
          actions={
            <Button size="s" variant="quiet" iconEnd="forward" onClick={() => onOpen("logs")}>
              {t("Open the diary")}
            </Button>
          }
        >
          <Problem error={problems.error} onRetry={problems.reload} />
          {problems.data && !recent.length ? (
            <State kind="empty" title={t("No problems lately.")} />
          ) : (
            <List label={t("Recent problems")}>
              {recent.map((line) => (
                <LogRow key={line.id} line={line} day />
              ))}
            </List>
          )}
        </Section>
      </div>
    </div>
  );
}

function Health({ onOpen }: { onOpen: (place: string) => void }) {
  const health = useData("/admin/health");
  const checks: Obj[] = health.data?.checks || [];
  return (
    <Section
      title={t("The state of the house")}
      actions={
        <Button size="s" variant="quiet" icon="refresh" onClick={() => void health.reload()}>
          {t("Refresh")}
        </Button>
      }
    >
      <Problem error={health.error} onRetry={health.reload} />
      {health.data?.checks && (
        <div className="control-summary">
          <Status tone="success">
            {checks.filter((c) => GOOD.has(c.status)).length} {t("all good")}
          </Status>
          <Status tone="warning">
            {checks.filter((c) => !GOOD.has(c.status) && !BAD.has(c.status)).length} {t("to check")}
          </Status>
          <Status tone="danger">
            {checks.filter((c) => BAD.has(c.status)).length} {t("problems")}
          </Status>
        </div>
      )}
      {!health.data && !health.error && <State kind="loading" />}
      <List label={t("The state of the house")}>
        {checks.map((c) => (
          <ListRow
            key={c.component}
            title={pretty(c.component)}
            detail={
              c.confirmed_by
                ? t("Confirmed working by") + " " + c.confirmed_by
                : t(c.evidence || "Connection has not been verified.")
            }
            status={{ tone: toneOf(c.status), text: t(pretty(c.status)) }}
            actions={
              !GOOD.has(c.status) && (
                <>
                  {/* A yellow or red check leads to where it is set up. */}
                  <Button size="s" iconEnd="forward" onClick={() => onOpen(c.tab || "services")}>
                    {t("Open its settings")}
                  </Button>
                  {["configured_unverified", "unverified"].includes(c.status) && (
                    <Button
                      size="s"
                      variant="quiet"
                      icon="check"
                      onClick={async () => {
                        await api("/admin/health/" + c.component + "/confirm", "POST");
                        await health.reload();
                      }}
                    >
                      {t("It works")}
                    </Button>
                  )}
                </>
              )
            }
          />
        ))}
      </List>
    </Section>
  );
}

// ---------- people ----------
const PERMISSIONS = [
  "household.read", "household.write", "messages.read", "messages.send", "files.read",
  "files.write", "files.shared.write", "music.read", "music.queue", "music.control", "cinema.use",
  "home.control", "assistant.use", "diagnostics.read", "invites.create",
]; // prettier-ignore

function Users() {
  const users = useData("/admin/users");
  const [edit, setEdit] = useState<Obj | null>(null);
  const all = items(users.data);
  const living = all.filter((u) => u.active && u.role !== "guest");
  const others = all.filter((u) => !u.active || u.role === "guest");
  const row = (u: Obj) => (
    <ListRow
      key={u.id}
      leading={<Icon name={u.role === "admin" ? "shield" : "person"} />}
      title={u.name}
      detail={"@" + u.username + " · " + t(ROLE_NAMES[u.role] || u.role)}
      status={u.active ? undefined : { tone: "neutral", text: t("Disabled") }}
      actions={
        <Button size="s" onClick={() => setEdit(u)}>
          {t("Manage")}
        </Button>
      }
    />
  );
  return (
    <Section title={t("People & permissions")}>
      <Problem error={users.error} onRetry={users.reload} />
      {/* The people who live here first; disabled accounts and old guests folded away. */}
      <List label={t("People & permissions")}>{living.map(row)}</List>
      {others.length > 0 && (
        <Disclosure summary={t("Guests and disabled accounts") + " (" + others.length + ")"}>
          <List label={t("Guests and disabled accounts")}>{others.map(row)}</List>
        </Disclosure>
      )}
      {edit && <ManageUser user={edit} onClose={() => setEdit(null)} onSaved={users.reload} />}
    </Section>
  );
}

const ROLE_NAMES: Record<string, string> = {
  admin: "Administrator",
  resident: "Resident",
  guest: "Guest",
};
const BUDGETS: Record<string, string> = {
  openai: "OpenAI",
  anthropic: "Anthropic",
  openrouter: "OpenRouter",
};
const sameSet = (a: unknown[], b: unknown[] = []) =>
  a.length === b.length && a.every((item) => b.includes(item));

/** One form, one Save in the sheet's foot: the role, access and permissions (changing them signs
 *  the person out) and their AI budgets. Only what changed is sent. */
function ManageUser({
  user,
  onClose,
  onSaved,
}: {
  user: Obj;
  onClose: () => void;
  onSaved: () => Promise<void>;
}) {
  const id = useId();
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const budgets = (read: (name: string) => number | undefined) => {
    const out: Obj = {};
    for (const name in BUDGETS) if (read(name) !== undefined) out[name] = read(name);
    return out;
  };
  return (
    <Sheet
      title={t("Manage {name}").replace("{name}", user.name)}
      place="side"
      onClose={onClose}
      footer={
        <>
          <Button variant="quiet" onClick={onClose}>
            {t("Cancel")}
          </Button>
          <Button type="submit" form={id} variant="primary" busy={busy}>
            {t("Save")}
          </Button>
        </>
      }
    >
      <form
        id={id}
        className="me-stack"
        onSubmit={async (e) => {
          e.preventDefault();
          const f = new FormData(e.currentTarget);
          const role = f.get("role"),
            active = f.get("active") === "on",
            permissions = f.getAll("permissions");
          const daily_microusd = budgets((name) =>
            f.get(name) === "" ? undefined : Math.round(Number(f.get(name)) * 1e6),
          );
          setBusy(true);
          setError("");
          try {
            if (
              role !== user.role ||
              active !== user.active ||
              !sameSet(permissions, user.permissions)
            )
              await api("/admin/users/" + user.id, "PUT", { active, role, permissions });
            const saved = budgets((name) => user.ai_daily_budgets?.[name]);
            if (JSON.stringify(daily_microusd) !== JSON.stringify(saved))
              await api("/admin/users/" + user.id + "/budgets", "PUT", { daily_microusd });
            toast(t("Saved."));
            onClose();
            await onSaved();
          } catch (failure) {
            setError((failure as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <Field label={t("Role")}>
          <Select name="role" defaultValue={user.role}>
            {Object.entries(ROLE_NAMES).map(([role, name]) => (
              <option key={role} value={role}>
                {t(name)}
              </option>
            ))}
          </Select>
        </Field>
        <Checkbox name="active" defaultChecked={user.active} label={t("Account active")} />
        <Disclosure summary={t("Explicit permissions and delegation")}>
          <fieldset className="me-fieldset">
            <legend className="visually-hidden">{t("Explicit permissions and delegation")}</legend>
            {PERMISSIONS.map((p) => (
              <Checkbox
                key={p}
                name="permissions"
                value={p}
                defaultChecked={user.permissions?.includes(p)}
                label={p}
              />
            ))}
          </fieldset>
        </Disclosure>
        <Disclosure summary={t("Individual AI budgets")}>
          <Text style="body-s" tone="muted">
            {t(
              "Blank inherits the provider default. Zero disables paid requests for this person. House-wide limits still apply.",
            )}
          </Text>
          {Object.entries(BUDGETS).map(([name, brand]) => (
            <Field label={brand + " · " + t("daily limit · USD")} key={name}>
              <Input
                type="number"
                min={0}
                step="0.01"
                name={name}
                defaultValue={
                  user.ai_daily_budgets?.[name] === undefined
                    ? ""
                    : user.ai_daily_budgets[name] / 1e6
                }
              />
            </Field>
          ))}
        </Disclosure>
        <Text style="body-s" tone="muted">
          {t("Changing the role, access or permissions signs this person out everywhere.")}
        </Text>
        <Problem error={error} />
      </form>
    </Sheet>
  );
}

const INVITE_PERMISSIONS = [
  "music.read", "music.queue", "household.read", "household.write", "messages.read",
  "messages.send", "files.read", "files.write", "cinema.use", "home.control", "assistant.use",
  "invites.create",
]; // prettier-ignore

function Invites() {
  const { data, error, reload } = useData("/auth/invites");
  const [invite, setInvite] = useState<Obj | null>(null),
    [qr, setQr] = useState(""),
    [copied, setCopied] = useState(false),
    [revoking, setRevoking] = useState<Obj | null>(null);
  const now = Date.now();
  const waiting = items(data).filter(
    (r) =>
      !r.revoked &&
      !r.redeemed &&
      new Date(
        /[zZ]|[+-]\d{2}:\d{2}$/.test(r.expires_at) ? r.expires_at : r.expires_at + "Z",
      ).getTime() > now,
  );
  const past = items(data).filter((r) => !waiting.includes(r));
  const inviteRow = (r: Obj) => (
    <ListRow
      key={r.id}
      leading={<Icon name="mail" />}
      title={t(pretty(r.preset))}
      detail={t("Expires") + " " + time(r.expires_at)}
      status={
        r.revoked
          ? { tone: "neutral", text: t("Revoked") }
          : r.redeemed
            ? { tone: "success", text: t("Redeemed") }
            : { tone: "info", text: t("Ready") }
      }
      actions={
        !r.revoked && (
          <Button size="s" variant="quiet" onClick={() => setRevoking(r)}>
            {t("Revoke")}
          </Button>
        )
      }
    />
  );
  return (
    <Section title={t("Open the door for someone")} lead={t("Invitations")}>
      <Form
        submit={t("Create invitation")}
        onSubmit={async (f) => {
          const r = await api("/auth/invites", "POST", {
            preset: f.get("preset"),
            expires_hours: Number(f.get("expires_hours")),
            membership_hours: f.get("membership_hours") ? Number(f.get("membership_hours")) : null,
            permissions: f.getAll("permissions"),
          });
          const url = location.origin + r.path;
          setInvite({ ...r, url });
          setCopied(false);
          const { default: QRCode } = await import("qrcode");
          setQr(await QRCode.toDataURL(url, { width: 220, margin: 2, color: qrColours() }));
          await reload();
        }}
      >
        <div className="me-row">
          <Field label={t("Preset")}>
            <Select name="preset">
              <option value="party">{t("Party guest · music queue only")}</option>
              <option value="guest">{t("Guest · music queue only")}</option>
              <option value="roommate">{t("Roommate · resident access")}</option>
              <option value="custom">{t("Custom permissions")}</option>
            </Select>
          </Field>
          <Field label={t("Link expires in")}>
            <Select name="expires_hours">
              <option value="2">{t("2 hours")}</option>
              <option value="24">{t("1 day")}</option>
              <option value="168">{t("7 days")}</option>
            </Select>
          </Field>
        </div>
        <Field label={t("Guest access duration (hours)")}>
          <Input
            name="membership_hours"
            type="number"
            min="1"
            max="720"
            placeholder={t("2 hours for guests; persistent for roommates")}
          />
        </Field>
        <Disclosure summary={t("Custom permission selection")}>
          <fieldset className="me-fieldset">
            <legend className="visually-hidden">{t("Custom permission selection")}</legend>
            {INVITE_PERMISSIONS.map((p) => (
              <Checkbox key={p} name="permissions" value={p} label={pretty(p)} />
            ))}
          </fieldset>
        </Disclosure>
      </Form>
      {invite && (
        <Surface material="raised" className="control-invite">
          <img src={qr} alt={t("QR code for this invitation")} />
          <div className="me-stack">
            <Text style="title-m">{t("Your invitation is ready.")}</Text>
            <Field label={t("Invitation link")}>
              <Input
                id="invite-link"
                readOnly
                value={invite.url}
                onFocus={(e) => e.target.select()}
              />
            </Field>
            <Text style="body-s" tone="muted">
              {t("Expires")} {time(invite.expires_at)}
              {t(". Share only with the intended guest.")}
            </Text>
            <div>
              <Button
                icon={copied ? "check" : "copy"}
                onClick={async () => {
                  try {
                    await navigator.clipboard.writeText(invite.url);
                    setCopied(true);
                  } catch {
                    setCopied(false);
                    document.getElementById("invite-link")?.focus();
                  }
                }}
              >
                {copied ? t("Copied") : t("Copy invitation link")}
              </Button>
            </div>
          </div>
        </Surface>
      )}
      <Problem error={error} onRetry={reload} />
      {/* Invitations still waiting first; used, expired or revoked ones folded away. */}
      {waiting.length > 0 ? (
        <List label={t("Invitations")}>{waiting.map(inviteRow)}</List>
      ) : (
        <Text tone="muted">{t("No invitation is waiting.")}</Text>
      )}
      {past.length > 0 && (
        <Disclosure summary={t("Past invitations") + " (" + past.length + ")"}>
          <List label={t("Past invitations")}>{past.map(inviteRow)}</List>
        </Disclosure>
      )}
      {revoking && (
        <ConfirmSheet
          title={t(
            revoking.redeemed
              ? "Revoke this invitation and its derived guest access?"
              : "Revoke this invitation?",
          )}
          confirm={t("Revoke")}
          danger
          onClose={() => setRevoking(null)}
          onConfirm={async () => {
            await api(
              "/auth/invites/" + revoking.id + "?revoke_membership=" + !!revoking.redeemed,
              "DELETE",
            );
            await reload();
          }}
        >
          <Text>{t(pretty(revoking.preset))}</Text>
        </ConfirmSheet>
      )}
    </Section>
  );
}

// ---------- connections ----------
/** What each connection gives the house, in one line. */
const PURPOSE: Record<string, string> = {
  stream_addon: "Finds films and series to stream (with a debrid service or the torrent player).",
  real_debrid: "Streams films instantly from its cloud; used through your stream add-on.",
  jellyfin: "Your own film library, playable here and on your TV.",
  home_assistant:
    "Lights, switches, blinds, heating and the TV: control them from HouseOS and Nox.",
  opensubtitles: "Extra subtitles when a film has none in your language.",
  comet: "Another film finder: a Stremio add-on server you run yourself.",
  cinemeta: "Posters, cast and synopses (free, nothing to set up).",
};

/** Each service by its own name (brands aren't translated); add-ons by what they are. */
const BRANDS: Record<string, string> = {
  real_debrid: "Debrid",
  jellyfin: "Jellyfin",
  home_assistant: "Home Assistant",
  opensubtitles: "OpenSubtitles",
};
const KINDS: Record<string, string> = {
  stream_addon: "Stream add-on",
  comet: "Your own add-on server",
};
const brand = (name: string) => BRANDS[name] || (KINDS[name] ? t(KINDS[name]) : pretty(name));

/** Each service's key: what it is called there, and where to find it. */
const SECRET_LABELS: Record<string, [string, string]> = {
  real_debrid: [
    "Debrid API token",
    "On your debrid service's API token page (real-debrid.com/apitoken).",
  ],
  stream_addon: ADDON_FIELD,
  jellyfin: ["Jellyfin API key", "In Jellyfin: Dashboard → API Keys → + (name it HouseOS)."],
  home_assistant: ["Home Assistant long-lived access token", ""],
  opensubtitles: ["OpenSubtitles API key", "On opensubtitles.com: your profile → API consumers."],
  comet: ["Its key (if it asks for one)", ""],
};

function Integrations() {
  const integrations = useData("/admin/integrations");
  const [edit, setEdit] = useState<Obj | null>(null),
    [testing, setTesting] = useState("");
  // ?open=<integration> (a link from Nox's setup mode) opens that integration's sheet once.
  const [opening, setOpening] = useState(() => new URLSearchParams(location.search).get("open"));
  useEffect(() => {
    const row = items(integrations.data).find((r) => r.name === opening);
    if (!row) return;
    setOpening(null);
    setEdit(row);
  }, [integrations.data, opening]);
  const rows = items(integrations.data)
    // AI has its own place; budgets live in Usage; "music" is internal state.
    .filter(
      (r) =>
        !AI_PROVIDERS.includes(r.name) &&
        !["budgets", "music", "cast", "cinemeta"].includes(r.name),
    );
  return (
    <Section title={t("Connections")}>
      <Problem error={integrations.error} onRetry={integrations.reload} />
      <List label={t("Connections")}>
        {rows.map((r) => (
          <ListRow
            key={r.name}
            leading={<Icon name="plug" />}
            title={brand(r.name)}
            detail={
              (PURPOSE[r.name] ? t(PURPOSE[r.name]) + " " : "") +
              (r.has_secret ? t("Credential stored securely") : t("No credential stored"))
            }
            // The state beside its buttons: on a phone they go under the text together, and
            // the explanation keeps the width.
            actions={
              <>
                <Status tone={toneOf(r.status)}>{t(pretty(r.status))}</Status>
                <Button size="s" onClick={() => setEdit(r)}>
                  {t("Configure")}
                </Button>
                <Button
                  size="s"
                  variant="quiet"
                  busy={testing === r.name}
                  onClick={async () => {
                    setTesting(r.name);
                    try {
                      const x = await api("/admin/integrations/" + r.name + "/test", "POST");
                      toast(
                        brand(r.name) +
                          ": " +
                          t(pretty(x.status)) +
                          (x.message ? " · " + x.message : x.scope ? " · " + x.scope : ""),
                        { tone: GOOD.has(x.status) ? "success" : "danger" },
                      );
                    } catch (e) {
                      toast((e as Error).message, { tone: "danger" });
                    } finally {
                      setTesting("");
                    }
                  }}
                >
                  {t("Test connection")}
                </Button>
              </>
            }
          />
        ))}
      </List>
      {edit && (
        <IntegrationEditor row={edit} onDone={integrations.reload} onClose={() => setEdit(null)} />
      )}
    </Section>
  );
}

/** A numbered how-to under a form. */
const Steps = ({ steps }: { steps: string[] }) => (
  <ol className="control-steps">
    {steps.map((step) => (
      <li key={step}>{t(step)}</li>
    ))}
  </ol>
);

function IntegrationEditor({
  row,
  onDone,
  onClose,
}: {
  row: Obj;
  onDone: () => void;
  onClose: () => void;
}) {
  const service = ["jellyfin", "comet", "home_assistant"].includes(row.name);
  // Jellyfin: a saved key is tested at once and lists whose library HouseOS shows.
  const [users, setUsers] = useState<Obj[] | null>(null),
    [players, setPlayers] = useState<Obj[] | null>(null),
    [domains, setDomains] = useState<Record<string, number>>({}),
    [saved, setSaved] = useState<Obj>({});
  // Home Assistant found on the network (Devices → Find devices) fills in its address.
  const ha = row.name === "home_assistant";
  const found = useData<Obj>(ha && !row.config?.base_url ? "/admin/devices/discover" : null);
  const foundUrl: string =
    items(found.data?.devices).find((device) => device.kind === "home_assistant")?.url || "";
  const [address, setAddress] = useState<string | null>(row.config?.base_url ?? null);
  const haUrl = (address ?? foundUrl).trim().replace(/\/+$/, "");
  return (
    <Sheet
      title={t("{name} configuration").replace("{name}", brand(row.name))}
      place="side"
      onClose={onClose}
    >
      <div className="me-stack">
        <Form
          submit={t(["jellyfin", "home_assistant"].includes(row.name) ? "Save and test" : "Save")}
          onSubmit={async (f) => {
            const config = JSON.parse(String(f.get("config")));
            for (const k of ["model", "base_url", "host"]) {
              if (f.has(k) && f.get(k)) config[k] = f.get(k);
            }
            for (const k of [
              "daily_budget_microusd",
              "user_daily_budget_microusd",
              "input_microusd_per_million",
              "cached_input_microusd_per_million",
              "cache_write_microusd_per_million",
              "output_microusd_per_million",
            ]) {
              if (f.has(k)) {
                if (f.get(k) !== "") config[k] = Math.round(Number(f.get(k)) * 1e6);
                else delete config[k];
              }
            }
            if (row.name === "real_debrid")
              config.entitlement_confirmed = f.get("entitlement_confirmed") === "on";
            if (row.name === "stream_addon")
              config.torrent_player = f.get("torrent_player") === "on";
            const enabled = f.get("enabled") === "on";
            await api("/admin/integrations/" + row.name, "PUT", {
              enabled,
              config,
              ...(f.get("clear_secret") === "on"
                ? { secret: "" }
                : f.get("secret")
                  ? { secret: f.get("secret") }
                  : {}),
            });
            onDone();
            if (row.name === "jellyfin" && enabled) {
              const test = await api("/admin/integrations/jellyfin/test", "POST");
              if (!test.users)
                throw new Error(
                  test.message ||
                    t(
                      test.status === "authentication_failed"
                        ? "Saved, but Jellyfin refused this API key."
                        : "Saved, but Jellyfin could not be reached at this address.",
                    ),
                );
              setSaved({ enabled, config });
              setUsers(test.users);
              return;
            }
            if (row.name === "home_assistant" && enabled) {
              const test = await api("/admin/integrations/home_assistant/test", "POST");
              if (!test.players)
                throw new Error(
                  test.message ||
                    t(
                      test.status === "authentication_failed"
                        ? "Saved, but Home Assistant refused this token."
                        : "Saved, but Home Assistant could not be reached at this address.",
                    ),
                );
              setSaved({ enabled, config });
              setPlayers(test.players);
              setDomains(test.domains || {});
              dispatchEvent(new Event("house-settings-updated")); // the Smart home room appears
              return;
            }
            onClose();
          }}
        >
          <Checkbox
            name="enabled"
            defaultChecked={row.enabled || (ha && !row.configured)}
            label={t("Enable integration")}
          />
          {service && (
            <Field
              label={t("Service address")}
              hint={t(
                "Any address this server can reach. Inside Docker, use host.docker.internal or the server's LAN address instead of 127.0.0.1.",
              )}
            >
              <Input
                name="base_url"
                type="url"
                {...(ha
                  ? { value: address ?? foundUrl, onChange: (e) => setAddress(e.target.value) }
                  : { defaultValue: row.config?.base_url })}
                placeholder={
                  (
                    {
                      jellyfin: "http://192.0.2.17:8096",
                      comet: "http://192.0.2.17:8767",
                      home_assistant: "http://192.168.1.20:8123",
                    } as Record<string, string>
                  )[row.name]
                }
              />
            </Field>
          )}
          {row.name === "cast" && (
            <Field label={t("Receiver LAN address")}>
              <Input name="host" defaultValue={row.config?.host} />
            </Field>
          )}
          {row.name === "real_debrid" && (
            <Checkbox
              name="entitlement_confirmed"
              defaultChecked={row.config?.entitlement_confirmed}
              label={t("I have verified that this account permits the intended use.")}
            />
          )}
          <Disclosure summary={t("Advanced integration options")}>
            <Field label={t("Additional configuration")}>
              <Textarea
                name="config"
                rows={6}
                defaultValue={JSON.stringify(row.config || {}, null, 2)}
                spellCheck={false}
              />
            </Field>
          </Disclosure>
          <Field
            label={t(SECRET_LABELS[row.name]?.[0] || "API key")}
            hint={SECRET_LABELS[row.name]?.[1] ? t(SECRET_LABELS[row.name][1]) : undefined}
          >
            <SecretInput
              name="secret"
              placeholder={row.has_secret ? t("Saved. Leave empty to keep it") : ""}
            />
          </Field>
          {ha && (
            <div className="me-stack">
              {address === null && foundUrl && (
                <Text style="body-s" tone="muted">
                  {t("Home Assistant was found on your network; its address is filled in.")}
                </Text>
              )}
              {/^https?:\/\/[^/\s]+$/.test(haUrl) && (
                <div>
                  <LinkButton
                    icon="forward"
                    href={haUrl + "/profile/security"}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    {t("Open Home Assistant's token page")}
                  </LinkButton>
                </div>
              )}
              <Steps
                steps={[
                  "Open the token page (sign in to Home Assistant if asked).",
                  "At the bottom, under Long-lived access tokens, press Create token and name it HouseOS.",
                  "Copy the token (Home Assistant shows it only once), paste it above, then Save and test.",
                ]}
              />
              <Text style="body-s" tone="muted">
                {t(
                  "If the page doesn't open from this device, open Home Assistant as usual and go to your profile → Security.",
                )}
              </Text>
            </div>
          )}
          {row.name === "stream_addon" && (
            <div className="me-stack">
              <BrowseAddons />
              <Steps
                steps={[
                  "Browse add-ons and pick a Stremio add-on that finds films and series.",
                  "On its page, pick your options. With a debrid service, choose it and paste your own API token.",
                  "Press Install and copy the link.",
                  "Paste that manifest link above, choose how films play below, and save.",
                ]}
              />
              <Checkbox
                name="torrent_player"
                defaultChecked={!!row.config?.torrent_player}
                label={t("Play torrents from this computer (the torrent player)")}
                hint={t(
                  "Without a debrid service, or when it doesn't have a version, this computer downloads the film from other people while it plays. They see this house's internet address, and it shares pieces back (slowly). Depending on where you live and what you watch, that can be illegal, and your internet provider may send you notices.",
                )}
              />
              <Text style="body-s" tone="muted">
                {t(
                  "Install it once first. Docker: ./houseos.sh torrents on. Linux: sudo python3 docs/native/setup_torrent_engine.py. Saving with the box ticked checks it's there.",
                )}
              </Text>
            </div>
          )}
          {row.has_secret && <Checkbox name="clear_secret" label={t("Remove stored credential")} />}
          <Text style="body-s" tone="muted">
            {t("Secrets are stored only on the server and are never returned here.")}
          </Text>
        </Form>
        {players && (
          <TvControlPick
            players={players}
            domains={domains}
            saved={saved}
            row={row}
            onDone={() => (onDone(), onClose())}
          />
        )}
        {users && (
          <Form
            submit={t("Use this person's library")}
            onSubmit={async (f) => {
              await api("/admin/integrations/jellyfin", "PUT", {
                ...saved,
                config: { ...saved.config, user_id: f.get("user_id") },
              });
              onDone();
              onClose();
            }}
          >
            <Field label={t("Jellyfin user")}>
              <Select name="user_id" defaultValue={row.config?.user_id}>
                {users.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.name}
                  </option>
                ))}
              </Select>
            </Field>
          </Form>
        )}
      </div>
    </Sheet>
  );
}
/** Kinds of Home Assistant device HouseOS may control, in the order offered. The last four
 *  are sensitive: off unless chosen, and every command on them asks for a confirmation. */
const HA_DOMAINS: [string, string][] = [
  ["light", "Lights"],
  ["switch", "Switches and plugs"],
  ["cover", "Blinds and shutters"],
  ["climate", "Heating and air conditioning"],
  ["fan", "Fans"],
  ["scene", "Scenes"],
  ["script", "Scripts"],
  ["media_player", "TVs and speakers"],
  ["vacuum", "Robot vacuums"],
  ["humidifier", "Humidifiers"],
  ["input_boolean", "On/off helpers"],
  ["button", "Buttons"],
  ["lock", "Locks"],
  ["alarm_control_panel", "Alarm"],
  ["siren", "Sirens"],
  ["valve", "Valves (water, gas)"],
];
const HA_SENSITIVE = new Set(["lock", "alarm_control_panel", "siren", "valve"]);
/** Home Assistant, after a successful test: what HouseOS may control (the Smart home room
 *  and Nox), and optionally which of its TVs is the HouseOS screen for films. */
function TvControlPick({
  players,
  domains,
  saved,
  row,
  onDone,
}: {
  players: Obj[];
  domains: Record<string, number>;
  saved: Obj;
  row: Obj;
  onDone: () => void;
}) {
  const devices = useData("/cinema/devices");
  const allowed: string[] =
    row.config?.domains ?? HA_DOMAINS.map(([d]) => d).filter((d) => !HA_SENSITIVE.has(d));
  const offered = HA_DOMAINS.filter(([domain]) => domains[domain]);
  return (
    <Form
      submit={t("Finish")}
      onSubmit={async (f) => {
        await api("/admin/integrations/home_assistant", "PUT", {
          ...saved,
          config: {
            ...saved.config,
            device_id: f.get("device_id") || "",
            receiver_id: f.get("receiver_id") || "",
            // Kinds this Home Assistant doesn't have keep their previous choice.
            domains: [...allowed.filter((d) => !domains[d]), ...(f.getAll("domains") as string[])],
          },
        });
        onDone();
      }}
    >
      <Notice tone="success">{t("Connected to Home Assistant.")}</Notice>
      {offered.length > 0 && (
        <fieldset className="me-fieldset">
          <legend>{t("What HouseOS and Nox may control")}</legend>
          {offered.map(([domain, label]) => (
            <Checkbox
              key={domain}
              name="domains"
              value={domain}
              defaultChecked={allowed.includes(domain)}
              label={t(label) + " (" + domains[domain] + ")"}
              hint={HA_SENSITIVE.has(domain) ? t("always asks to confirm") : undefined}
            />
          ))}
        </fieldset>
      )}
      {players.length > 0 && (
        <>
          <Text style="body-s" tone="muted">
            {t(
              "Optional: Home Assistant can also turn your film TV on and off, change its volume and switch its input (HDMI) before a film.",
            )}
          </Text>
          <Field label={t("The TV in Home Assistant")}>
            <Select name="device_id" defaultValue={row.config?.device_id || ""}>
              <option value="">{t("No TV")}</option>
              {players.map((player) => (
                <option key={player.id} value={player.id}>
                  {player.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field
            label={t("The same TV in HouseOS")}
            hint={
              !items(devices.data).length
                ? t("Add the TV in Devices first (Find devices), then come back.")
                : undefined
            }
          >
            <Select name="receiver_id" defaultValue={row.config?.receiver_id || ""}>
              <option value="">{t("No TV")}</option>
              {items(devices.data).map((device) => (
                <option key={device.id} value={device.id}>
                  {device.name}
                </option>
              ))}
            </Select>
          </Field>
        </>
      )}
    </Form>
  );
}

// ---------- Logs: what the house did, as sentences, newest first ----------
const LOG_KINDS: [string, string, IconName][] = [
  ["", "Everything", "sparkles"],
  ["music", "Music", "music"],
  ["films", "Films", "film"],
  ["games", "Games", "gamepad"],
  ["nox", "Nox", "bot"],
  ["house", "House", "list-todo"],
  ["system", "System", "settings"],
];
const TRANSLATED_VALUES = new Set(["what", "status", "action"]);
/** One line of the house's diary: what happened (×3 when it repeated), then who acted, what it
 * was trying to do, why it failed, and whether it needs you or was fixed since. */
function LogRow({ line, day }: { line: Obj; day?: boolean }) {
  const clock = (at: string) =>
    date(at, { hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" });
  const icon: IconName =
    line.care === "needs"
      ? "alert"
      : line.care === "handled"
        ? "check"
        : LOG_KINDS.find(([key]) => key === line.category)?.[2] || "dot";
  const code = line.values?.code;
  // Why first: it's what you read the line for; then who and what they were trying.
  const detail = [
    code && message(code),
    line.who || (line.actor && t(line.actor)),
    line.tried && t(line.tried),
    line.values?.where,
    line.resolved_at
      ? t("Fixed at {time}").replace("{time}", clock(line.resolved_at).slice(0, 5))
      : line.care === "handled" && t("Handled by itself"),
  ].filter(Boolean);
  return (
    <ListRow
      leading={
        <span className="control-log__icon" data-care={line.care}>
          <Icon name={icon} size="s" />
        </span>
      }
      title={logText(line) + (line.count > 1 ? " ×" + line.count : "")}
      detail={detail.join(" · ") || undefined}
      meta={
        <time
          className="tabular"
          dateTime={line.at}
          title={(line.times || []).map(clock).join(", ") || undefined}
        >
          {day ? time(line.at) : clock(line.at)}
        </time>
      }
    />
  );
}

function logText(line: Obj) {
  let text = t(line.template);
  for (const [key, value] of Object.entries(line.values || {}))
    text = text.replace(
      "{" + key + "}",
      TRANSLATED_VALUES.has(key) ? t(String(value)) : String(value),
    );
  return text;
}
function logDay(at: string) {
  const day = new Date(at).toDateString();
  const today = new Date();
  const yesterday = new Date(Date.now() - 86400000);
  return day === today.toDateString()
    ? t("Today")
    : day === yesterday.toDateString()
      ? t("Yesterday")
      : date(at, { weekday: "long", day: "numeric", month: "long" });
}
function ActivityLog() {
  const [kind, setKind] = useState(""),
    [needs, setNeeds] = useState(false),
    [search, setSearch] = useState("");
  const query = new URLSearchParams({
    ...(kind ? { category: kind } : {}),
    ...(needs ? { needs: "true" } : {}),
    ...(search.trim() ? { search: search.trim() } : {}),
  }).toString();
  const base = "/admin/activity" + (query ? "?" + query : "");
  const pages = usePages(base, (data) => (data.next ? "before=" + data.next : null));
  const head = useData(base, { interval: 30000 }); // new lines arrive at the top by themselves
  const seen = new Set<number>();
  const lines = [...items(head.data), ...pages.items]
    .filter((line) => !seen.has(line.id) && seen.add(line.id))
    .sort((a, b) => b.id - a.id);
  let lastDay = "";
  return (
    <Section title={t("What happened")} lead={t("The house's diary, with no private content.")}>
      <ChipGroup label={t("Show")}>
        {LOG_KINDS.map(([key, label, icon]) => (
          <Chip
            key={key}
            kind="filter"
            icon={icon}
            selected={kind === key}
            onToggle={() => setKind(key)}
          >
            {t(label)}
          </Chip>
        ))}
        <Chip kind="filter" icon="alert" selected={needs} onToggle={() => setNeeds((on) => !on)}>
          {t("Needs you")}
        </Chip>
      </ChipGroup>
      <SearchInput
        label={t("Search the log")}
        placeholder={t("Search: a song, a film, a name, a tool…")}
        value={search}
        onChange={setSearch}
      />
      <Problem error={pages.error || head.error} />
      {lines.length > 0 && (
        <List label={t("What happened")}>
          {lines.flatMap((line) => {
            const day = logDay(line.at);
            const header = day !== lastDay;
            lastDay = day;
            return [
              header && <ListHeading key={"day-" + line.id}>{day}</ListHeading>,
              <LogRow key={line.id} line={line} />,
            ];
          })}
        </List>
      )}
      <MoreBelow pages={pages} />
      {!lines.length && !pages.loading && (
        <State
          kind="empty"
          title={t(needs ? "Nothing needs you. All quiet." : "Nothing matches.")}
        />
      )}
    </Section>
  );
}

// ---------- devices ----------
const FOUND_KINDS: Record<string, () => string> = {
  tv: () => t("screen"),
  audio: () => t("speaker"),
  group: () => t("speaker group"),
  dlna: () => t("speaker or TV (DLNA)"),
  airplay: () => "AirPlay",
  screen: () => t("TV or streaming box"),
  home_assistant: () => "Home Assistant",
  jellyfin: () => "Jellyfin",
};
// How each maker's devices work with HouseOS, in one line: what plays here, and which Home
// Assistant integration adds power, sources and arrows (Smart home and the TV remote use it).
const BRAND_HINTS: Record<string, () => string> = {
  lg: () =>
    t(
      "LG webOS: add Home Assistant's “LG webOS TV” integration for power, sources, volume and arrows.",
    ),
  samsung: () =>
    t("Samsung: Home Assistant's “Samsung Smart TV” integration adds power, sources and arrows."),
  sony: () =>
    t("Sony Bravia: Home Assistant's “Sony Bravia TV” integration adds power, sources and arrows."),
  roku: () => t("Roku: Home Assistant's “Roku” integration adds power, apps and arrows."),
  philips: () =>
    t("Philips: Home Assistant's “Philips TV” integration adds power, sources and arrows."),
  hisense: () =>
    t(
      "Hisense: films play through its Chromecast or DLNA; Home Assistant's VIDAA integration adds power and inputs.",
    ),
  panasonic: () =>
    t("Panasonic: Home Assistant's “Panasonic Viera” integration adds power and volume."),
  tcl: () => t("TCL (Google TV): pair its arrows in the TV remote; films play through Chromecast."),
  sonos: () => t("Sonos: plays the house music here. Grouping stays in the Sonos app."),
  apple: () =>
    t(
      "Apple TV: HouseOS can't play on AirPlay yet; Home Assistant's “Apple TV” integration adds power and arrows.",
    ),
  amazon: () =>
    t(
      "Fire TV: open HouseOS in its Silk browser; Home Assistant's “Android Debug Bridge” integration adds control.",
    ),
  heos: () => t("Denon / Marantz (HEOS): plays the house music here through DLNA."),
  yamaha: () => t("Yamaha MusicCast: plays the house music here through DLNA."),
  bose: () => t("Bose: plays through Chromecast or AirPlay when the speaker has them."),
  google: () =>
    t("Google TV / Android TV: films and music play here; pair its arrows in the TV remote."),
};
/** The line under a found device: its maker's hint, or the Cast speakers' own. */
function hint(d: Obj) {
  if ((d.kind === "audio" || d.kind === "group") && d.brand === "google")
    return t("Cast speaker: the house music plays here, in step with the others.");
  return BRAND_HINTS[d.brand]?.() || "";
}
function DeviceAdmin() {
  const { data, error, reload } = useData("/cinema/devices");
  const found = useData<Obj>("/admin/devices/discover");
  const remotes = useData<Obj>("/tv");
  const [edit, setEdit] = useState<Obj | null>(null),
    [failure, setFailure] = useState(""),
    [pairing, setPairing] = useState<Obj | null>(null);
  // The device's own remote (not the TV-itself remote Home Assistant adds for the same screen).
  const remote = (id: string) =>
    items(remotes.data).find((tv) => tv.id === id && tv.target !== "tv")?.capabilities;
  // A speaker group lives at one of its speakers' address, on its own port.
  const key = (adapter: string, address: string, port?: number) =>
    adapter + " " + address + (port && port !== 8009 ? ":" + port : "");
  const saved = new Set(items(data).map((d) => key(d.adapter, d.address, d.capabilities?.port)));
  const adapter = (d: Obj) => (d.kind === "dlna" ? "dlna" : "cast");
  const scanning = !!found.data?.scanning;
  // While a scan runs (about 6 s on the media relay), look again every second.
  useEffect(() => {
    if (!scanning) return;
    const timer = setTimeout(() => void found.reload(), 1000);
    return () => clearTimeout(timer);
  }, [scanning, found.data]);
  const add = async (device: Obj) => {
    setFailure("");
    try {
      await api("/cinema/devices", "POST", {
        name: device.name,
        adapter: adapter(device),
        address: device.address,
        session_id: null,
        capabilities: {
          kind: device.kind, // TV remotes leave out speakers and groups
          ...(device.port ? { port: device.port } : {}),
          ...(device.description_url ? { description_url: device.description_url } : {}),
        },
      });
      await reload();
    } catch (e) {
      setFailure((e as Error).message);
    }
  };
  const foundDevices: Obj[] = found.data?.devices || [];
  return (
    <>
      <Section
        title={t("TVs, speakers and services on your Wi-Fi")}
        lead={t(
          "Finds Chromecast, Google TV and Nest, Sonos, smart TVs (LG, Samsung, Sony, Philips, Hisense, Roku…) and hi-fi speakers (DLNA), AirPlay, Home Assistant and Jellyfin. HouseOS and the devices must be on the same network.",
        )}
        actions={
          <Button
            variant="primary"
            icon="refresh"
            busy={scanning}
            disabled={found.data?.scanner_running === false}
            onClick={async () => {
              await api("/admin/devices/discover", "POST");
              await found.reload();
            }}
          >
            {scanning ? t("Looking…") : t("Find devices")}
          </Button>
        }
      >
        {found.data?.announced && (
          <Text style="body-s" tone="muted">
            {t("Phones on this Wi-Fi open HouseOS at")} <code>{found.data.announced}</code>
          </Text>
        )}
        <Problem error={found.error || failure} onRetry={found.reload} />
        {found.data?.scanner_running === false && (
          <Notice tone="warning">
            {t(
              "The media relay isn't running, so HouseOS can't look for devices. Restart it in Services.",
            )}
          </Notice>
        )}
        {found.data?.problem && (
          <Notice tone="warning">{t("The last search failed. Try again.")}</Notice>
        )}
        {!scanning && found.data?.scanned_at && !foundDevices.length && (
          <Notice>
            {t(
              "Nothing answered. Check the TV is on and on the same network (not a guest Wi-Fi). A TV without Chromecast plays the music through DLNA; films need Chromecast built in or the Jellyfin app on the TV.",
            )}
          </Notice>
        )}
        {foundDevices.length > 0 && (
          <List label={t("Found on your network")}>
            {foundDevices.map((d: Obj) => (
              <ListRow
                key={d.kind + d.address + d.name}
                leading={
                  <Icon name={["audio", "group", "dlna"].includes(d.kind) ? "speaker" : "tv"} />
                }
                title={d.name}
                detail={[d.model, d.address, FOUND_KINDS[d.kind]?.()].filter(Boolean).join(" · ")}
                actions={
                  d.url ? (
                    <LinkButton
                      size="s"
                      variant="quiet"
                      href={d.url}
                      target="_blank"
                      rel="noreferrer"
                    >
                      {t("Open")}
                    </LinkButton>
                  ) : d.kind === "screen" ? null : !d.playable ? (
                    <Badge tone="neutral">{t("Found; HouseOS can't play on it yet")}</Badge>
                  ) : saved.has(key(adapter(d), d.address, d.port)) ? (
                    <Badge tone="success">{t("Added")}</Badge>
                  ) : (
                    <Button size="s" icon="add" onClick={() => void add(d)}>
                      {t("Add")}
                    </Button>
                  )
                }
              >
                {hint(d) && (
                  <Text style="body-s" tone="muted">
                    {hint(d)}
                  </Text>
                )}
              </ListRow>
            ))}
          </List>
        )}
      </Section>
      <Section
        title={t("Your devices")}
        lead={t("Choose where music plays in Speakers; films ask which screen each time.")}
        actions={
          <Button size="s" icon="add" onClick={() => setEdit({})}>
            {t("Add by address")}
          </Button>
        }
      >
        <Problem error={error} onRetry={reload} />
        {data && !items(data).length && (
          <State kind="empty" title={t("None yet: use Find devices above.")} />
        )}
        <List label={t("Your devices")}>
          {items(data).map((d) => (
            <ListRow
              key={d.id}
              leading={<Icon name={d.adapter === "dlna" ? "speaker" : "tv"} />}
              title={d.name}
              detail={
                d.address +
                " · " +
                (d.adapter === "cast"
                  ? t("Cast")
                  : d.adapter === "dlna"
                    ? "DLNA"
                    : t("Jellyfin client"))
              }
              actions={
                <>
                  {remote(d.id)?.remote_pairable && (
                    <Button size="s" variant="quiet" onClick={() => setPairing(d)}>
                      {remote(d.id)?.paired
                        ? t("Pair its remote again")
                        : steersScreen(items(remotes.data), d)
                          ? t("Pair its own arrows (optional)")
                          : t("Set up the remote")}
                    </Button>
                  )}
                  <Button size="s" icon="edit" onClick={() => setEdit(d)}>
                    {t("Edit")}
                  </Button>
                </>
              }
            />
          ))}
        </List>
        {pairing && (
          <PairDialog
            tv={pairing}
            onClose={() => setPairing(null)}
            onPaired={() => void remotes.reload()}
          />
        )}
        {edit && (
          <Sheet
            title={edit.id ? t("Edit device") : t("Add by address")}
            place="side"
            onClose={() => setEdit(null)}
          >
            <div className="me-stack">
              <Form
                onSubmit={async (f) => {
                  await api(
                    "/cinema/devices" + (edit.id ? "/" + edit.id : ""),
                    edit.id ? "PUT" : "POST",
                    {
                      name: f.get("name"),
                      adapter: f.get("adapter") || "cast",
                      address: f.get("address"),
                      session_id: f.get("session_id") || null,
                      capabilities: JSON.parse(String(f.get("capabilities") || "{}")),
                      ...(edit.id ? { version: edit.version } : {}),
                    },
                  );
                  setEdit(null);
                  await reload();
                }}
              >
                <Field label={t("Name, as the house will see it")}>
                  <Input
                    name="name"
                    defaultValue={edit.name}
                    placeholder={t("Living-room TV")}
                    required
                  />
                </Field>
                <Field
                  label={t("Its address on your network (IP)")}
                  hint={t(
                    "Find it in the TV's settings: Network → Status, or in your router's device list.",
                  )}
                >
                  <Input
                    name="address"
                    required
                    defaultValue={edit.address}
                    placeholder="192.0.2.21"
                    inputMode="decimal"
                  />
                </Field>
                <Disclosure summary={t("Advanced")}>
                  <Field label={t("Playback adapter")}>
                    <Select name="adapter" defaultValue={edit.adapter || "cast"}>
                      <option value="cast">{t("Chromecast")}</option>
                      <option value="dlna">{t("DLNA speaker or TV (music)")}</option>
                      <option value="jellyfin">{t("Jellyfin client")}</option>
                    </Select>
                  </Field>
                  <Field label={t("Jellyfin session ID (if applicable)")}>
                    <Input name="session_id" defaultValue={edit.session_id} />
                  </Field>
                  <Field label={t("Verified capability profile")}>
                    <Textarea
                      name="capabilities"
                      rows={5}
                      defaultValue={JSON.stringify(edit.capabilities || {}, null, 2)}
                      spellCheck={false}
                    />
                  </Field>
                </Disclosure>
              </Form>
              {edit.id && (
                <RemoveDevice
                  device={edit}
                  onRemoved={async () => (setEdit(null), await reload())}
                />
              )}
            </div>
          </Sheet>
        )}
      </Section>
    </>
  );
}
/** Forget a device (a TV replaced, a speaker given away): asks once more before it goes. */
function RemoveDevice({ device, onRemoved }: { device: Obj; onRemoved: () => Promise<unknown> }) {
  const [sure, setSure] = useState(false);
  return (
    <>
      <div>
        <Button variant="quiet" icon="trash" onClick={() => setSure(true)}>
          {t("Remove this device")}
        </Button>
      </div>
      {sure && (
        <ConfirmSheet
          title={t("Remove {name} for good").replace("{name}", device.name)}
          confirm={t("Remove")}
          danger
          onClose={() => setSure(false)}
          onConfirm={async () => {
            await api("/cinema/devices/" + device.id, "DELETE");
            await onRemoved();
          }}
        >
          <Text>{t("It can be found and added again later.")}</Text>
        </ConfirmSheet>
      )}
    </>
  );
}

// ---------- services ----------
const SERVICE_NAMES: Record<string, () => string> = {
  api: () => t("Web app"),
  worker: () => t("Music and jobs"),
  maintenance: () => t("Chores, reminders and clean-up"),
  fetch: () => t("Music sources (YouTube, SoundCloud, radio)"),
  audio: () => t("Speakers"),
  upload: () => t("File uploads"),
  media: () => t("Media relay (TV and Cast)"),
  "cinema-worker": () => t("Film preparation"),
  "cinema-observer": () => t("TV playback watcher"),
  voice: () => t("Voice typing"),
  codex: () => t("ChatGPT sign-in"),
  claude: () => t("Claude sign-in"),
};
/** What each part does, in one line, so a stopped one says what stops working. */
const SERVICE_ROLES: Record<string, string> = {
  api: "The pages you are using and every button.",
  worker: "Plays the queue, fetches songs and runs background jobs.",
  maintenance: "Reminders, clean-up, backups and the film index.",
  fetch: "Reaches YouTube, SoundCloud and radio for songs.",
  audio: "Sends the music to the speakers.",
  upload: "Receives large files.",
  media: "Hands films and music to the TV and Cast speakers.",
  "cinema-worker": "Checks film versions and prepares them.",
  "cinema-observer": "Follows what the TV is playing.",
  voice: "Turns speech into text.",
  codex: "Keeps the ChatGPT sign-in for Nox.",
  claude: "Keeps the Claude sign-in for Nox.",
};
type ServiceState = { tone: "good" | "bad" | "off" | "wait"; text: string; fix?: string };
const SERVICE_TONES: Record<ServiceState["tone"], Tone> = {
  good: "success",
  bad: "danger",
  off: "neutral",
  wait: "info",
};
/** Measured state in words: Docker probes (ok/down/off) or systemd's own answer. */
function serviceState(s: Obj): ServiceState {
  const again = t("If it stops again, open Logs → Needs you, or ask Nox in setup mode.");
  if ("restartable" in s) {
    if (s.status === "ok") {
      const d = s.detail || {};
      const text =
        s.name === "audio"
          ? d.sound_server === "none"
            ? t("Running; no speakers on this server (phones and Cast still play)")
            : t("Running; plays on this computer's speakers")
          : s.name === "voice" && d.preparing
            ? t("Downloading its speech model (a few minutes, once)")
            : s.name === "voice" && d.device
              ? d.device === "gpu"
                ? t("Running on the graphics card")
                : t("Running on the processor")
              : t("Running");
      return { tone: "good", text };
    }
    return {
      tone: "bad",
      text: s.status === "off" ? t("Not running") : t("Not answering"),
      fix: t("Press Restart.") + " " + again,
    };
  }
  if (s.status !== "observed") return { tone: "off", text: t("Status unknown") };
  const active = s.active ?? s.properties?.ActiveState; // the helper's field (older: properties)
  if (active === "active") return { tone: "good", text: t("Running") };
  if (active === "activating" || active === "reloading")
    return { tone: "wait", text: t("Starting…") };
  return {
    tone: "bad",
    text:
      active === "failed"
        ? t("Stopped after an error") +
          (s.exit_code && s.exit_code !== "0" ? ` (${s.exit_code})` : "")
        : t("Stopped"),
    fix: t("Press Restart.") + " " + again,
  };
}
/** One line above the list: all well, or how many parts need you. */
function ServiceSummary({ states }: { states: ServiceState[] }) {
  const bad = states.filter((s) => s.tone === "bad").length;
  const unread = states.filter((s) => s.tone === "off").length;
  const text = bad
    ? t("{n} of {total} parts need attention: see the red ones below.")
    : unread
      ? t("The service helper didn't answer, so states are unknown. The house may be fine.") +
        " " +
        t("On the server: sudo systemctl restart houseos-control")
      : t("All {total} parts are running.");
  return (
    <Notice tone={bad ? "danger" : unread ? "warning" : "success"}>
      {text.replace("{n}", String(bad)).replace("{total}", String(states.length))}
    </Notice>
  );
}
function ServiceAdmin() {
  const services = useData("/admin/services");
  const [operationId, setOperationId] = useState("");
  const operation = useData(operationId ? "/operations/" + operationId : null);
  const [selected, setSelected] = useState<Obj | null>(null),
    [preview, setPreview] = useState<Obj | null>(null);
  return (
    <>
      <HouseActions />
      <Section
        title={t("House services")}
        actions={
          <Button size="s" variant="quiet" icon="refresh" onClick={() => void services.reload()}>
            {t("Refresh observations")}
          </Button>
        }
      >
        <Problem error={services.error || operation.error} onRetry={services.reload} />
        {operation.data && (
          <Surface material="sunken" className="me-stack control-operation">
            <Status tone={toneOf(operation.data.state)}>{t(pretty(operation.data.state))}</Status>
            <ReviewDetails value={operation.data.result || {}} />
            <div>
              <Button
                size="s"
                variant="quiet"
                icon="refresh"
                onClick={() => void operation.reload()}
              >
                {t("Verify operation")}
              </Button>
            </div>
          </Surface>
        )}
        {services.data && <ServiceSummary states={items(services.data).map(serviceState)} />}
        <List label={t("House services")}>
          {items(services.data).map((s) => {
            const state = serviceState(s);
            return (
              <ListRow
                key={s.name}
                title={SERVICE_NAMES[s.name]?.() || pretty(s.name)}
                detail={t(SERVICE_ROLES[s.name] || "")}
                status={{
                  tone: SERVICE_TONES[state.tone],
                  text: state.text,
                  busy: state.tone === "wait",
                }}
                actions={
                  (s.restartable || s.status === "observed") && (
                    <Button
                      size="s"
                      variant={state.tone === "bad" ? "primary" : "secondary"}
                      icon="refresh"
                      onClick={() => {
                        setSelected(s);
                        setPreview(null);
                      }}
                    >
                      {t("Restart…")}
                    </Button>
                  )
                }
              >
                {state.fix && (
                  <Text style="body-s" tone="danger">
                    {state.fix}
                  </Text>
                )}
              </ListRow>
            );
          })}
        </List>
        {selected && (
          <Sheet
            title={t("Restart {name}").replace(
              "{name}",
              SERVICE_NAMES[selected.name]?.() || pretty(selected.name),
            )}
            onClose={() => setSelected(null)}
          >
            {preview ? (
              <Form
                submit={t("Confirm this exact restart")}
                onSubmit={async () => {
                  const r = await api(
                    "/admin/services/confirmations/" + preview.confirmation_id,
                    "POST",
                  );
                  toast(
                    t(pretty(r.status)) +
                      ". " +
                      t("Refresh service observations to verify the outcome."),
                  );
                  setOperationId(r.operation_id);
                  setSelected(null);
                  await services.reload();
                }}
              >
                <ReviewDetails value={preview.preview} />
                <Text>
                  {t("Confirmation expires in two minutes. Active media prevents this action.")}
                </Text>
              </Form>
            ) : (
              <Form
                submit={t("Prepare restart")}
                onSubmit={async () =>
                  setPreview(
                    await api("/admin/services/" + selected.name + "/prepare-restart", "POST", {}),
                  )
                }
              >
                <Text>
                  {t(
                    "This may interrupt requests using this component. Review the exact impact before confirming.",
                  )}
                </Text>
              </Form>
            )}
          </Sheet>
        )}
      </Section>
      {items(services.data).some((s) => !("restartable" in s)) && <ShutdownHouseOS />}
    </>
  );
}

/** Backups in words: when the last one ran, and how to make one on this kind of install. */
/** Backups, in one place: the last one, how they run, the ones kept, how many to keep, and how
 * to restore. The server refuses a second backup within ten minutes, so a double tap is safe. */
function RecoveryAdmin() {
  const r = useData("/admin/recovery");
  const house = useData("/admin/house-settings");
  const d = r.data;
  const keep = async (value: number) => {
    await api("/admin/house-settings", "PUT", { backup_keep: value });
    await house.reload();
    toast(t("Saved: it applies from the next backup."));
  };
  return (
    <>
      <Section
        title={t("Backups")}
        lead={t("Keep the house safe.")}
        actions={
          <Button size="s" variant="quiet" icon="refresh" onClick={() => void r.reload()}>
            {t("Refresh")}
          </Button>
        }
      >
        <Problem error={r.error} onRetry={r.reload} />
        {d?.created_at ? (
          <Notice
            tone="success"
            title={t("Last backup: {when}").replace("{when}", time(d.created_at))}
          >
            {d.location && (
              <>
                {t("Saved in:")} <code>{d.location}</code>
              </>
            )}
          </Notice>
        ) : (
          d && <Notice tone="warning">{t("No backup has been made on this install yet.")}</Notice>
        )}
        <Text>
          {t(
            d?.container
              ? "Backups run when you press Back up now (or run ./houseos.sh backup on the server). Everything pauses for about a minute."
              : "A backup runs by itself every night at 04:15, encrypted, on the storage drive.",
          )}{" "}
          {t(
            "Each one holds the database, the state (it holds the keys that unlock saved passwords: keep it private) and the files. Copy the backups folder to another disk or computer now and then.",
          )}
        </Text>
        {d?.container && <HouseActions only={["backup"]} />}
      </Section>
      <Section title={t("The backups kept")}>
        {(d?.backups || []).length > 0 ? (
          <List label={t("The backups kept")}>
            {[...d!.backups].reverse().map((b: Obj) => (
              <ListRow
                key={b.name}
                leading={<Icon name="archive" />}
                title={b.name}
                detail={b.bytes ? bytes(b.bytes) : undefined}
              />
            ))}
          </List>
        ) : (
          <Text tone="muted">{t("The list appears after the next backup.")}</Text>
        )}
        {house.data && (
          <Field
            label={t("Keep")}
            hint={t("Older backups are deleted only when you choose a number here.")}
          >
            <Select
              value={String(house.data.backup_keep ?? 0)}
              onChange={(e) => void keep(Number(e.target.value))}
            >
              <option value="0">{t("Every backup")}</option>
              {[3, 7, 14, 30].map((n) => (
                <option key={n} value={n}>
                  {t("The last {n}").replace("{n}", String(n))}
                </option>
              ))}
            </Select>
          </Field>
        )}
      </Section>
      <Section title={t("Restoring")}>
        <Disclosure summary={t("How to restore a backup")}>
          {d?.container ? (
            <Stack>
              <Text>
                {t(
                  "On a fresh install, before its first start, in the HouseOS folder (replace <date> with the backup's name):",
                )}
              </Text>
              <pre className="control-code">
                {`docker compose create
docker compose run --rm --no-deps -u 0 -v "$PWD/backups/<date>":/b --entrypoint tar db  xzf /b/houseos-db.tgz -C /var/lib/mysql
docker compose run --rm --no-deps -u 0 -v "$PWD/backups/<date>":/b --entrypoint tar api xzf /b/houseos-files.tgz -C /
docker compose up -d`}
              </pre>
            </Stack>
          ) : (
            <Text>
              {t(
                "This house's backups are encrypted: restoring needs its backup key, from the machine's secret store. The steps are in docs/OPERATIONS-PERSONAL.md (Backups and upgrades).",
              )}
            </Text>
          )}
        </Disclosure>
        {d?.created_at && (
          <Disclosure summary={t("Details")}>
            <ReviewDetails
              value={Object.fromEntries(Object.entries(d).filter(([k]) => k !== "backups"))}
            />
          </Disclosure>
        )}
      </Section>
    </>
  );
}

/** Making a theme (admins): remix one by hand, design one with Nox, or learn how in the workshop. */
const KIT_FOLDER = "houseos.kit.folder";

/** Your own AI agent (Claude Code, Codex…) makes a theme from the HouseOS folder: its path
 *  (this device remembers it: the app can't see where HouseOS sits on the disk), a prompt to
 *  paste that points it at the kit and walks you through the brainstorm, and the visual guide. */
function AgentKit() {
  const [folder, setFolder] = useState(() => {
    try {
      return localStorage.getItem(KIT_FOLDER) || "";
    } catch {
      return "";
    }
  });
  const where = folder.trim() || t("my HouseOS folder");
  const prompt = t(
    "You're making a complete theme for HouseOS with me, installed in {folder}. Read themes/AGENT-KIT.md there first and follow its method. Ask me a few short questions, one at a time (the feeling, light or dark, what I love, what I don't want), then show me three different directions before building anything. Build the one I pick: plan every part of the house, draw the pictures with the art toolkit, add layers that move where they help, run the checks and the tour, look at every screenshot, and show me the best ones at each step. Keep every screen readable, and keep your messages short.",
  ).replace("{folder}", where);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(prompt);
      toast(t("Copied: paste it into your agent, started in that folder."));
    } catch {
      toast(t("Select the text and copy it by hand."), { tone: "neutral" });
    }
  };
  return (
    <Section
      title={t("With your own AI agent")}
      lead={t(
        "Claude Code, Codex or another coding agent can build a whole theme with you, from the folder HouseOS is installed in. It reads the theme kit and asks you the right questions.",
      )}
    >
      <Field
        label={t("Your HouseOS folder")}
        hint={t("The one with houseos.sh in it. Remembered on this device.")}
      >
        <Input
          value={folder}
          placeholder="~/HouseOS"
          onChange={(e) => {
            setFolder(e.target.value);
            try {
              localStorage.setItem(KIT_FOLDER, e.target.value);
            } catch {
              /* private window: this visit only */
            }
          }}
        />
      </Field>
      <ol className="control-kit__steps">
        <li>{t("Open a terminal in that folder.")}</li>
        <li>{t("Start your coding agent there.")}</li>
        <li>{t("Paste this:")}</li>
      </ol>
      <pre className="control-kit__prompt">{prompt}</pre>
      <Cluster space={2}>
        <Button variant="primary" icon="copy" onClick={() => void copy()}>
          {t("Copy the prompt")}
        </Button>
        <LinkButton
          icon="download"
          href="/guides/make-a-theme.html"
          download="HouseOS - Make your own theme.html"
        >
          {t("Download the visual guide")}
        </LinkButton>
      </Cluster>
    </Section>
  );
}

function MakeATheme() {
  const [starting, setStarting] = useState(false),
    [nox, setNox] = useState(false),
    [agent, setAgent] = useState(false);
  const current = useTheme().split("/")[0];
  return (
    <>
      <section className="me-make" aria-label={t("Make a theme")}>
        <div className="me-make__preview" aria-hidden="true">
          <ThemePreview theme={current} scale={0.3} />
        </div>
        <div className="me-make__words">
          <Text as="h2" style="title-l">
            {t("Make a theme")}
          </Text>
          <Text tone="muted">
            {t(
              "Colours, type, pictures for every surface, words, even Nox and the house's medals: remix a theme by hand, make one with Nox, or see how a theme is built.",
            )}
          </Text>
          <Cluster space={2}>
            <Button variant="primary" icon="brush" onClick={() => setStarting(true)}>
              {t("Remix a theme")}
            </Button>
            <Button icon="sparkles" pressed={nox} onClick={() => setNox(!nox)}>
              {t("Make one with Nox")}
            </Button>
            <Button icon="bot" pressed={agent} onClick={() => setAgent(!agent)}>
              {t("With your own AI agent")}
            </Button>
            <Button variant="quiet" icon="compass" onClick={() => go("/workshop")}>
              {t("Open the workshop")}
            </Button>
          </Cluster>
        </div>
      </section>
      {starting && <StartTheme source={current} onClose={() => setStarting(false)} />}
      {nox && <Studio />}
      {agent && <AgentKit />}
    </>
  );
}

// ---------- speakers ----------
// What the audio bridge found, and what its failure answers mean, in plain words.
const SOUND: Record<string, string> = {
  pulse: "Music plays on this computer's speakers (its normal sound output). Nothing to set up.",
  alsa: "No sound server is running, so music plays straight on this computer's sound card.",
  none: "This computer has no speakers HouseOS can use. Music still keeps time here: play it on phones and computers with Speaker mode, or on a Cast speaker.",
};
const BRIDGE: Record<string, string> = {
  AUDIO_BRIDGE_UNAVAILABLE:
    "The music player on this computer is not running, so its speakers cannot be listed. Start the audio service, then refresh.",
  AUDIO_COMMAND_FAILED:
    "The music player could not list this computer's speakers. Refresh in a moment.",
};
const OUTPUT_KINDS: Record<string, () => string> = {
  bluetooth: () => t("Bluetooth"),
  hdmi: () => t("HDMI (screen or TV)"),
  usb: () => t("USB"),
};
function AudioAdmin() {
  // Re-read now and then: a speaker paired over Bluetooth appears here by itself.
  const outputs = useData("/admin/audio", { interval: 15000 });
  const [error, setError] = useState(""),
    [tested, setTested] = useState(false);
  const d = outputs.data;
  const link = location.origin + "/speaker";
  const act = async (fn: () => Promise<unknown>, done: string) => {
    try {
      await fn();
      setError("");
      toast(t(done));
    } catch (e) {
      setError((e as Error).message);
    }
    await outputs.reload();
  };
  // One tap is the confirmation: prepare, then confirm straight away.
  const speaker = async (action: "select" | "test", sink: string) => {
    const prepared = await api("/admin/audio/prepare", "POST", { action, sink });
    const result = await api("/admin/audio/confirm/" + prepared.confirmation_id, "POST");
    if (result.code) throw new Error(pretty(result.code));
    return result;
  };
  const here = d?.device_id ? "" : d?.selected || "default";
  // Without speakers, "this computer" and "no sound" are the same choice: show one.
  const choices = items(d).filter((o) => o.id !== "default" || o.state !== "SILENT");
  const networked: Obj[] = d?.devices || [];
  return (
    <Section
      title={t("Where does the music play?")}
      actions={
        <Button size="s" variant="quiet" icon="refresh" onClick={() => void outputs.reload()}>
          {t("Refresh")}
        </Button>
      }
    >
      <Problem error={outputs.error || error} onRetry={outputs.reload} />
      {d?.code && BRIDGE[d.code] && <Notice tone="warning">{t(BRIDGE[d.code])}</Notice>}
      {d?.sound_server && <Text>{t(SOUND[d.sound_server])}</Text>}
      {d && d.playback_enabled === false && (
        <Notice tone="warning">
          {t("Music playback is switched off in this house's settings.")}
        </Notice>
      )}
      {d && (
        <>
          <Section
            level={3}
            title={t("This computer")}
            lead={t(
              "Every output of this computer, even while music plays. A Bluetooth speaker paired with this computer appears here by itself.",
            )}
          >
            {!choices.length && (
              <Text style="body-s" tone="muted">
                {t("No outputs to list right now.")}
              </Text>
            )}
            <List label={t("This computer")}>
              {choices.map((o) => {
                const chosen =
                  here === o.id ||
                  (here === "default" && o.id === "none" && d.sound_server === "none");
                return (
                  <ListRow
                    key={o.id}
                    leading={<Icon name="speaker" />}
                    title={t(o.name)}
                    detail={OUTPUT_KINDS[o.kind]?.()}
                    selected={chosen}
                    actions={
                      <Button
                        size="s"
                        variant={chosen ? "primary" : "secondary"}
                        pressed={chosen}
                        disabled={chosen}
                        onClick={() =>
                          void act(() => speaker("select", o.id), "Music plays here now.")
                        }
                      >
                        {chosen ? t("Playing here") : t("Play here")}
                      </Button>
                    }
                  />
                );
              })}
            </List>
          </Section>
          <Section level={3} title={t("Speakers and TVs on the Wi-Fi")}>
            {networked.length ? (
              <List label={t("Speakers and TVs on the Wi-Fi")}>
                {networked.map((device) => {
                  const chosen = d.device_id === device.id;
                  return (
                    <ListRow
                      key={device.id}
                      leading={<Icon name={device.adapter === "dlna" ? "speaker" : "cast"} />}
                      title={device.name}
                      detail={device.adapter === "dlna" ? "DLNA" : t("Cast")}
                      selected={chosen}
                      actions={
                        <Button
                          size="s"
                          variant={chosen ? "primary" : "secondary"}
                          pressed={chosen}
                          onClick={() =>
                            void act(
                              () =>
                                api("/admin/audio/device", "PUT", {
                                  device_id: chosen ? null : device.id,
                                }),
                              chosen
                                ? "Music no longer plays on this device."
                                : "Music plays on this device now.",
                            )
                          }
                        >
                          {chosen ? t("Stop playing here") : t("Play here")}
                        </Button>
                      }
                    />
                  );
                })}
              </List>
            ) : (
              <Text style="body-s" tone="muted">
                {t(
                  "Add a speaker or TV in Devices (Find devices) to play music on it: Chromecast, Google TV, Nest, Sonos and most smart TVs and hi-fi speakers.",
                )}
              </Text>
            )}
            {d.device_id && !d.relay_ready && (
              <Notice tone="warning">
                {t(
                  "Speakers and TVs on the Wi-Fi need the media relay running on this computer. Start it, then refresh.",
                )}
              </Notice>
            )}
          </Section>
          <Section
            level={3}
            title={t("Phones and computers")}
            lead={t(
              "Open this link on any phone or computer signed in to the house and tap Play here. It plays along with the house.",
            )}
          >
            <div className="control-link">
              <code>{link}</code>
              <Button
                size="s"
                icon="copy"
                onClick={() =>
                  void navigator.clipboard
                    ?.writeText(link)
                    .then(() => toast(t("Link copied.")))
                    .catch(() => setError(t("Copy the link by hand.")))
                }
              >
                {t("Copy link")}
              </Button>
            </div>
          </Section>
          {!d.device_id && here !== "none" && d.sound_server !== "none" && (
            <Disclosure summary={t("Play a test sound (optional)")}>
              <Text style="body-s" tone="muted">
                {t(
                  "Music must be stopped. You will hear one quiet second on the speakers chosen above.",
                )}
              </Text>
              <div className="control-link">
                <Button
                  size="s"
                  icon="volume"
                  onClick={() =>
                    void act(async () => {
                      await speaker("test", here);
                      setTested(true);
                    }, "Test sound sent.")
                  }
                >
                  {t("Play a test sound")}
                </Button>
                {tested &&
                  [true, false].map((heard) => (
                    <Button
                      key={String(heard)}
                      size="s"
                      variant="quiet"
                      onClick={() =>
                        void act(
                          () => api("/admin/audio/verify", "POST", { sink: here, heard }),
                          heard
                            ? "Thanks, noted."
                            : "Noted. Check the speakers are on and not muted.",
                        )
                      }
                    >
                      {heard ? t("I heard it") : t("I didn't hear it")}
                    </Button>
                  ))}
              </div>
            </Disclosure>
          )}
        </>
      )}
    </Section>
  );
}

// ---------- background work ----------
const JOB_NAMES: Record<string, string> = {
  "music.metadata": "Looking up a song",
  "music.control": "A music command",
  "music.download": "Keeping a song",
  "music.playlist_import": "Importing a playlist",
  "service.restart": "Restarting a service",
  "cinema.validate": "Checking a film version",
  "cinema.discover": "Finding film versions",
};
const JOB_STATES: [string, string][] = [
  ["", "Waiting or running"],
  ["failed", "Failed"],
  ["completed", "Done"],
  ["all", "Everything"],
];
const jobTone = (state: string): Tone =>
  state === "failed" ? "danger" : state === "completed" ? "success" : "info";

/** What HouseOS is doing in the background, in words; details folded for the curious. */
function JobsAdmin() {
  const [state, setState] = useState("");
  const jobs = useData(
    "/admin/jobs?state=" + encodeURIComponent(state === "all" ? "" : state || "active"),
  );
  const rows = items(jobs.data);
  return (
    <Section
      title={t("Background work")}
      lead={t("What HouseOS is doing.")}
      actions={
        <Button size="s" variant="quiet" icon="refresh" onClick={() => void jobs.reload()}>
          {t("Refresh")}
        </Button>
      }
    >
      <Segmented
        label={t("Show")}
        value={state}
        onChange={setState}
        options={JOB_STATES.map(([value, label]) => ({ value, label: t(label) }))}
      />
      <Problem error={jobs.error} onRetry={jobs.reload} />
      {rows.length > 0 && (
        <List label={t("Background work")}>
          {rows.map((j) => (
            <ListRow
              key={j.id}
              title={t(JOB_NAMES[j.kind] || "Background task")}
              detail={
                time(j.next_run) +
                (j.attempts > 1 ? " · " + t("try") + " " + j.attempts : "") +
                (j.error_code ? " · " + pretty(j.error_code) : "")
              }
              status={{ tone: jobTone(j.state), text: t(pretty(j.state)) }}
            >
              <Disclosure summary={t("Details")}>
                <code className="control-code">
                  {j.kind} · {j.id}
                </code>
              </Disclosure>
            </ListRow>
          ))}
        </List>
      )}
      {jobs.data && !rows.length && (
        <State kind="empty" title={t("Nothing is waiting: all caught up.")} />
      )}
    </Section>
  );
}

// ---------- the house's look (Themes) ----------
/** The house's theme: what everyone sees until they choose their own. */
function ThemesAdmin() {
  const settings = useData("/admin/house-settings");
  const mine = useData("/preferences");
  const [busy, setBusy] = useState(false);
  const theme = allThemes().find((item) => item.id === renamed(settings.data?.theme));
  // Your own choice in Me wins over the house's: say so, or changing it here seems to do nothing.
  const own = allThemes().find((item) => item.id === renamed(mine.data?.theme));
  const save = async (change: Obj) => {
    setBusy(true);
    try {
      await api("/admin/house-settings", "PUT", change);
      window.dispatchEvent(new Event("house-settings-updated"));
      await settings.reload();
      toast(t("Saved for the whole house."));
    } catch (e) {
      toast((e as Error).message, { tone: "danger" });
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <Section
        title={t("Default theme for new people")}
        lead={t(
          "New people start with this one, and so does anyone who follows the house. Each person can still pick their own in Your preferences → Appearance; guests always see this one.",
        )}
      >
        <Problem error={settings.error} onRetry={settings.reload} />
        {own && own.id !== theme?.id && (
          <Notice
            tone="info"
            action={
              <Button
                size="s"
                onClick={async () => {
                  await api("/preferences", "PUT", { theme: "", scheme: "" });
                  window.dispatchEvent(new Event("house-settings-updated"));
                  await mine.reload();
                }}
              >
                {t("Follow the house")}
              </Button>
            }
          >
            {t("You wear {name} yourself, so the house's theme doesn't show for you.").replace(
              "{name}",
              getLanguage() === "fr" ? own.names.fr : own.names.en,
            )}
          </Notice>
        )}
        {settings.data && (
          <>
            <ThemePicker
              label={t("The house's theme")}
              value={settings.data.theme}
              scheme={settings.data.scheme}
              onChange={(id) => void save({ theme: id })}
            />
            <SchemeChoice
              theme={theme}
              value={settings.data.scheme || ""}
              onChange={(scheme) => void save({ scheme })}
            />
          </>
        )}
        {busy && (
          <Status tone="info" busy>
            {t("Saving…")}
          </Status>
        )}
      </Section>
      <MakeATheme />
      <Section
        title={t("Your themes")}
        lead={t("Drafts stay yours until you share one with the house.")}
      >
        <MadeHere />
      </Section>
      <Section
        title={t("Shared and asked for")}
        lead={t("The themes the house shares, and the ones waiting for you.")}
      >
        <MadeHere admin />
      </Section>
    </>
  );
}
