// Your own integrations (Control Room → Integrations): code a household adds for its own devices,
// installed from a git repository (backend custom.py, custom_admin.py). Check shows what a
// repository holds before anything runs; installed ones stay off until turned on. Each has its
// keys (for shortcuts and helpers that can't sign in) and the card it reports.
import { useState } from "react";
import { t, getLanguage } from "./i18n";
import { api, useData, items, time, type Obj } from "./api";
import {
  Badge,
  Button,
  Cluster,
  ConfirmSheet,
  Disclosure,
  Field,
  Form,
  Icon,
  Input,
  List,
  ListRow,
  Notice,
  Problem,
  SecretInput,
  Section,
  Sheet,
  Stack,
  Status,
  Surface,
  Switch,
  Text,
  toast,
  type Tone,
} from "./design";

/** An integration's own words: a string, or {en, fr, …} by language. */
export const own = (value: unknown) =>
  typeof value === "string"
    ? value
    : value && typeof value === "object"
      ? String((value as Obj)[getLanguage()] ?? (value as Obj).en ?? "")
      : "";

const short = (commit?: string) => (commit || "").slice(0, 7);

export function CustomIntegrations() {
  const { data, error, reload } = useData<Obj>("/admin/custom-integrations");
  const [adding, setAdding] = useState(false),
    [open, setOpen] = useState<string | null>(null);
  const rows = items(data);
  const shown = rows.find((r) => r.id === open);
  return (
    <Section
      title={t("Your own integrations")}
      lead={t(
        "Code you or someone you trust wrote for this house's own devices, installed from a git repository. It runs with HouseOS's full rights: add only what you trust.",
      )}
      actions={
        <Button icon="add" onClick={() => setAdding(true)}>
          {t("Add from a repository")}
        </Button>
      }
    >
      <Problem error={error} onRetry={reload} />
      {rows.length > 0 && (
        <List label={t("Your own integrations")}>
          {rows.map((r) => (
            <ListRow
              key={r.id}
              leading={<Icon name="plug" />}
              title={(r.manifest?.name || r.id) + (r.manifest?.version ? " · " + r.manifest.version : "")}
              detail={r.manifest?.description}
              status={
                r.problem
                  ? { tone: "danger", text: t("Didn't start") }
                  : r.loaded
                    ? { tone: "success", text: t("On") }
                    : { tone: "neutral", text: t("Off") }
              }
              actions={
                <Button size="s" onClick={() => setOpen(r.id)}>
                  {t("Open")}
                </Button>
              }
            />
          ))}
        </List>
      )}
      {adding && (
        <AddIntegration
          onClose={() => setAdding(false)}
          onDone={async (id) => (await reload(), setAdding(false), setOpen(id))}
        />
      )}
      {shown && <IntegrationSheet row={shown} reload={reload} onClose={() => setOpen(null)} />}
    </Section>
  );
}

/** What a checked repository holds, before it is installed or updated. */
function Preview({ found }: { found: Obj }) {
  const m = found.manifest || {},
    s = found.source || {};
  return (
    <Surface material="raised">
      <Stack>
        <Text style="title-s">
          {m.name} {m.version && <Badge tone="neutral">{m.version}</Badge>}
        </Text>
        {m.description && <Text>{m.description}</Text>}
        <Text style="body-s" tone="muted">
          {s.url}
          {s.ref ? " @ " + s.ref : ""} · {short(s.commit)} {s.subject}
        </Text>
        {found.current && (
          <Text style="body-s" tone="muted">
            {t("Installed now")}: {short(found.current)}
          </Text>
        )}
        <Disclosure summary={t("Files")}>
          <Text style="body-s">
            <code>{(found.files || []).join("\n")}</code>
          </Text>
        </Disclosure>
      </Stack>
    </Surface>
  );
}

function AddIntegration({ onClose, onDone }: { onClose: () => void; onDone: (id: string) => unknown }) {
  const [found, setFound] = useState<Obj | null>(null),
    [failure, setFailure] = useState("");
  return (
    <Sheet title={t("Add an integration")} onClose={onClose} wide>
      <Stack>
        {!found ? (
          <Form
            submit={t("Check the repository")}
            onSubmit={async (fields) => {
              setFailure("");
              try {
                setFound(
                  await api<Obj>("/admin/custom-integrations/check", "POST", {
                    url: String(fields.get("url") || ""),
                    ref: String(fields.get("ref") || "") || null,
                    token: String(fields.get("token") || "") || null,
                  }),
                );
              } catch (e) {
                setFailure((e as Error).message);
              }
            }}
          >
            <Field label={t("Repository address")} hint={t("Its https address, as you would clone it.")}>
              <Input name="url" type="url" required placeholder="https://git.example.net/me/my-integration.git" />
            </Field>
            <Field label={t("Branch or tag (optional)")}>
              <Input name="ref" />
            </Field>
            <Field
              label={t("Access token (optional)")}
              hint={t("For a private repository: a read-only token. Kept encrypted, used only to download it.")}
            >
              <SecretInput name="token" />
            </Field>
          </Form>
        ) : (
          <>
            <Preview found={found} />
            <Notice tone="warning">
              {t(
                "Nothing from it has run yet. Once turned on, it runs inside HouseOS with access to the house's data and connections.",
              )}
            </Notice>
            <Cluster>
              <Button variant="quiet" onClick={() => setFound(null)}>
                {t("Back")}
              </Button>
              <Button
                variant="primary"
                onClick={async () => {
                  setFailure("");
                  try {
                    const row = await api<Obj>("/admin/custom-integrations/install", "POST", {
                      check_id: found.check_id,
                    });
                    toast(t("Installed. Turn it on when you're ready."));
                    await onDone(row.id);
                  } catch (e) {
                    setFailure((e as Error).message);
                  }
                }}
              >
                {t("Install, turned off")}
              </Button>
            </Cluster>
          </>
        )}
        <Problem error={failure} />
      </Stack>
    </Sheet>
  );
}

function IntegrationSheet({ row, reload, onClose }: { row: Obj; reload: () => Promise<unknown>; onClose: () => void }) {
  const [failure, setFailure] = useState(""),
    [update, setUpdate] = useState<Obj | null>(null),
    [checking, setChecking] = useState(false),
    [removing, setRemoving] = useState(false),
    [key, setKey] = useState("");
  const base = "/admin/custom-integrations/" + row.id;
  const act = async (work: () => Promise<unknown>) => {
    setFailure("");
    try {
      await work();
    } catch (e) {
      setFailure((e as Error).message);
    } finally {
      await reload();
    }
  };
  const copy = (value: string) =>
    void navigator.clipboard
      ?.writeText(value)
      .then(() => toast(t("Copied.")))
      .catch(() => setFailure(t("Select the text and copy it by hand.")));
  const card = row.card || {};
  return (
    <Sheet title={row.manifest?.name || row.id} onClose={onClose} wide>
      <Stack>
        {row.manifest?.description && <Text>{row.manifest.description}</Text>}
        <Switch
          checked={!!row.enabled}
          label={t("Turned on")}
          hint={t("Its routes, Nox tools, share buttons and card work only while it is on.")}
          onChange={(on) => void act(() => api(base + "/enabled", "PUT", { enabled: on }))}
        />
        {row.problem && <Notice tone="danger">{t("It didn't start:") + " " + row.problem}</Notice>}
        {(card.lines || []).map((line: Obj, i: number) => (
          <Status key={i} tone={(line.tone as Tone) || "neutral"}>
            {own(line.label)}: {own(line.value)}
          </Status>
        ))}
        {(card.help || []).length > 0 && (
          <Disclosure summary={t("How to use it")}>
            <ol className="control-steps">
              {card.help.map((step: unknown, i: number) => (
                <li key={i}>{own(step)}</li>
              ))}
            </ol>
          </Disclosure>
        )}
        <Section level={3} title={t("Keys")} lead={t("For phone shortcuts, scripts and helpers on other computers, which can't sign in. A key only opens what this integration allows, and acts as you.")}>
          {(row.keys || []).length > 0 && (
            <List label={t("Keys")}>
              {row.keys.map((k: Obj) => (
                <ListRow
                  key={k.id}
                  leading={<Icon name="key" />}
                  title={k.name}
                  detail={t("Created by") + " " + k.by + ", " + time(new Date(k.created_at * 1000).toISOString())}
                  actions={
                    <Button
                      size="s"
                      variant="quiet"
                      onClick={() => void act(() => api(base + "/keys/" + k.id, "DELETE"))}
                    >
                      {t("Remove")}
                    </Button>
                  }
                />
              ))}
            </List>
          )}
          <Form
            reset
            submit={t("Create a key")}
            onSubmit={(fields) =>
              act(async () => {
                const made = await api<Obj>(base + "/keys", "POST", { name: String(fields.get("name") || "") });
                setKey(made.key);
              })
            }
          >
            <Field label={t("What it's for")}>
              <Input name="name" required maxLength={60} placeholder={t("My phone")} />
            </Field>
          </Form>
          {key && (
            <Surface material="raised">
              <Stack>
                <Field label={t("New key")} hint={t("Shown only this once.")}>
                  <Input readOnly value={key} onFocus={(e) => e.target.select()} />
                </Field>
                <div>
                  <Button icon="copy" onClick={() => copy(key)}>
                    {t("Copy the key")}
                  </Button>
                </div>
              </Stack>
            </Surface>
          )}
        </Section>
        <Section level={3} title={t("Source")}>
          <Text style="body-s" tone="muted">
            {row.source?.url}
            {row.source?.ref ? " @ " + row.source.ref : ""} · {short(row.source?.commit)} {row.source?.subject}
            {row.updated_at ? " · " + time(row.updated_at) : ""}
          </Text>
          {update && (
            <>
              <Preview found={update} />
              <Cluster>
                <Button variant="quiet" onClick={() => setUpdate(null)}>
                  {t("Cancel")}
                </Button>
                <Button
                  variant="primary"
                  onClick={() =>
                    void act(async () => {
                      await api(base + "/update", "POST", { check_id: update.check_id });
                      setUpdate(null);
                      toast(t("Updated."));
                    })
                  }
                >
                  {t("Update to this version")}
                </Button>
              </Cluster>
            </>
          )}
          <Cluster>
            {row.source?.kind === "git" && !update && (
              <Button
                icon="refresh"
                busy={checking}
                onClick={() =>
                  void act(async () => {
                    setChecking(true);
                    try {
                      setUpdate(await api<Obj>(base + "/check-update", "POST"));
                    } finally {
                      setChecking(false);
                    }
                  })
                }
              >
                {t("Check for an update")}
              </Button>
            )}
            <Button variant="danger" onClick={() => setRemoving(true)}>
              {t("Remove")}
            </Button>
          </Cluster>
        </Section>
        <Problem error={failure} />
      </Stack>
      {removing && (
        <ConfirmSheet
          title={t("Remove this integration?")}
          confirm={t("Remove")}
          danger
          onClose={() => setRemoving(false)}
          onConfirm={async () => {
            await api(base, "DELETE");
            setRemoving(false);
            onClose();
            await reload();
          }}
        >
          <Text>{t("Its code, keys and data go. What it wrote in the activity diary stays.")}</Text>
        </ConfirmSheet>
      )}
    </Sheet>
  );
}

/** Capture: the share buttons turned-on integrations offer for this text. */
export function ShareButtons({ text }: { text: string }) {
  const { data } = useData<Obj>("/custom-integrations/shares");
  const [busy, setBusy] = useState(""),
    [said, setSaid] = useState<{ tone: Tone; text: string } | null>(null);
  const matching = items(data).filter((s) => {
    try {
      return new RegExp(s.match).test(text);
    } catch {
      return false;
    }
  });
  if (!matching.length) return null;
  return (
    <>
      {matching.map((s) => (
        <Button
          key={s.integration + s.id}
          icon="send"
          busy={busy === s.integration + s.id}
          onClick={async () => {
            setBusy(s.integration + s.id);
            setSaid(null);
            try {
              const reply = await api<Obj>(`/custom/${s.integration}${s.path}`, "POST", { [s.field]: text });
              setSaid({ tone: "success", text: own(reply?.message) || t("Sent.") });
            } catch (e) {
              setSaid({ tone: "warning", text: (e as Error).message });
            } finally {
              setBusy("");
            }
          }}
        >
          {own(s.label)}
        </Button>
      ))}
      {said && <Notice tone={said.tone}>{said.text}</Notice>}
    </>
  );
}
