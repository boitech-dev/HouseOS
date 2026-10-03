// Control Room → Changes (admins): code changes Nox drafted, with their full diff. Apply backs
// up, checks, deploys and checks the health on the house computer; the backup stays until Keep.
import { useState } from "react";
import { t } from "./i18n";
import { api, useData, time, type Obj } from "./api";
import {
  Button,
  Cluster,
  ConfirmSheet,
  Disclosure,
  Notice,
  Problem,
  Section,
  Stack,
  State,
  Status,
  Text,
  type Tone,
} from "./design";
import "./setup.css";

const STATES: Record<string, [Tone, () => string]> = {
  draft: ["neutral", () => t("Waiting for you")],
  working: ["info", () => t("In progress")],
  applied: ["success", () => t("Applied: keep it or undo it")],
  failed: ["danger", () => t("Not applied")],
  undone: ["neutral", () => t("Undone")],
  kept: ["success", () => t("Kept")],
};
// Per action: the working line, the confirmation's title, its button and what it does.
const ACTIONS: Record<string, [() => string, () => string, () => string, () => string]> = {
  apply: [
    () => t("Backing up, checking, then restarting HouseOS (several minutes)…"),
    () => t("Apply this change?"),
    () => t("Apply"),
    () =>
      t(
        "HouseOS backs up, checks the change, then restarts with it (music resumes where it was). If it doesn't come back, it goes back to the backup by itself.",
      ),
  ],
  keep: [
    () => t("Deleting the backup…"),
    () => t("Keep this change?"),
    () => t("Keep"),
    () => t("This deletes the backup: afterwards the change can only be undone by hand."),
  ],
  undo: [
    () => t("Going back to the backup…"),
    () => t("Undo this change?"),
    () => t("Undo"),
    () => t("HouseOS goes back to how it was before this change and restarts."),
  ],
};

export function ChangesAdmin() {
  const s = useData("/admin/changes", {
    interval: (d) => (d?.changes?.some((c: Obj) => c.state === "working") ? 3000 : false),
  });
  const [ask, setAsk] = useState<{ change: Obj; action: string } | null>(null);
  const d = s.data;
  if (!d) return <Problem error={s.error} />;
  if (!d.ready) return <State kind="not-configured">{t(d.problem)}</State>;
  // Apply sends back the digest of the diff shown here: a draft changed since is refused.
  const act = (c: Obj, action: string) =>
    api(`/admin/changes/${c.id}/${action}`, "POST", { digest: c.digest }).finally(s.reload);
  const [, title, confirm, effect] = ACTIONS[ask?.action || "apply"];
  return (
    <Stack>
      {d.docker && d.helper === false && (
        <Notice tone="warning">
          {t(
            "To apply changes, turn on Control Room buttons: on the server, run ./houseos.sh buttons on",
          )}
        </Notice>
      )}
      {!d.changes.length && (
        <State kind="empty" title={t("No changes yet")}>
          {t(
            "In setup mode, ask Nox to change how HouseOS works: it drafts the change here for you to review.",
          )}
        </State>
      )}
      {d.changes.map((c: Obj) => {
        const [tone, label] = STATES[c.state] || STATES.draft;
        return (
          <Section
            key={c.id}
            title={c.summary}
            lead={`${c.author} · ${time(new Date(c.created * 1000).toISOString())}`}
          >
            <Stack>
              <Status tone={tone} busy={c.state === "working"}>
                {c.state === "working" ? ACTIONS[c.action]?.[0]() : label()}
              </Status>
              {c.stuck && (
                <Notice tone="warning">
                  {t(
                    "The house computer hasn't picked this up. Code changes may not be set up on it: see docs/CHANGING-HOUSEOS.md.",
                  )}
                </Notice>
              )}
              {c.stale && (
                <Notice tone="warning">
                  {t("HouseOS changed since this was drafted: ask Nox to draft it again")}
                </Notice>
              )}
              {c.message && (
                <Disclosure summary={t(c.message)}>
                  <pre className="setup-log">{c.log}</pre>
                </Disclosure>
              )}
              {(c.diff || []).map((f: Obj) => (
                <Stack key={f.path}>
                  <Text style="label">
                    {f.path}
                    {f.new && ` · ${t("new file")}`}
                  </Text>
                  <pre className="setup-log">{f.diff}</pre>
                </Stack>
              ))}
              <Cluster>
                {["draft", "undone", "failed"].includes(c.state) && !c.stale && (
                  <Button
                    variant="primary"
                    disabled={d.helper === false}
                    onClick={() => setAsk({ change: c, action: "apply" })}
                  >
                    {t("Apply")}
                  </Button>
                )}
                {c.backed && c.state !== "working" && (
                  <>
                    <Button variant="primary" onClick={() => setAsk({ change: c, action: "keep" })}>
                      {t("Keep")}
                    </Button>
                    <Button onClick={() => setAsk({ change: c, action: "undo" })}>
                      {t("Undo")}
                    </Button>
                  </>
                )}
                {!c.backed && c.state !== "working" && (
                  <Button variant="quiet" icon="trash" onClick={() => act(c, "discard")}>
                    {c.state === "kept" ? t("Remove from the list") : t("Discard")}
                  </Button>
                )}
              </Cluster>
            </Stack>
          </Section>
        );
      })}
      {ask && (
        <ConfirmSheet
          title={title()}
          confirm={confirm()}
          danger={ask.action === "keep"}
          onConfirm={() => act(ask.change, ask.action)}
          onClose={() => setAsk(null)}
        >
          <Text as="p">{effect()}</Text>
          <ul>
            {ask.change.files.map((f: string) => (
              <li key={f}>
                <code>{f}</code>
              </li>
            ))}
          </ul>
        </ConfirmSheet>
      )}
    </Stack>
  );
}
