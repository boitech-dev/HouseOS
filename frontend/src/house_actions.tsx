import { useState } from "react";
import { t } from "./i18n";
import { message } from "./messages";
import { api, useData, type Obj } from "./api";
import {
  Button,
  Cluster,
  Disclosure,
  Field,
  Form,
  Input,
  Notice,
  Problem,
  Section,
  Sheet,
  Status,
  Surface,
  Switch,
  Text,
} from "./design";
import "./setup.css";

const NAMES: Record<string, () => string> = {
  update: () => t("Update HouseOS"),
  backup: () => t("Back up now"),
  "gpu-on": () => t("Move voice to the graphics card"),
  "gpu-off": () => t("Move voice to the processor"),
  "own-address": () => t("Give HouseOS its own address"),
  "own-address-off": () => t("Use this computer's address"),
};
const COMMANDS: Record<string, string> = {
  update: "./houseos.sh update",
  backup: "./houseos.sh backup",
  "gpu-on": "./houseos.sh gpu on",
  "own-address": "./houseos.sh own-address",
};

function CopyCommand({ command }: { command: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <Surface material="sunken" className="setup-command">
      <code className="setup-code">{command}</code>
      <Button
        size="s"
        variant="quiet"
        icon={copied ? "check" : "copy"}
        onClick={() => void navigator.clipboard?.writeText(command).then(() => setCopied(true))}
      >
        {copied ? t("Copied") : t("Copy")}
      </Button>
    </Surface>
  );
}

/**
 * Docker installs: houseos.sh's actions as buttons (through the optional helper), or the one
 * command to run on the server when the helper is off. `only` limits the buttons shown.
 */
export function HouseActions({ only }: { only?: string[] }) {
  const s = useData("/admin/house-actions", {
    interval: (d) => (d?.tasks?.some((x: Obj) => x.state === "running") ? 3000 : 60000),
  });
  const [open, setOpen] = useState(""),
    [checking, setChecking] = useState(false);
  const d = s.data;
  if (!d?.container) return null;
  const shown = (a: string) => !only || only.includes(a);
  const running = (d.tasks || []).find((x: Obj) => x.state === "running");
  const about = d.about || {};
  const wrap = (body: React.ReactNode) =>
    only ? body : <Section title={t("Updates and more")}>{body}</Section>;
  if (!d.helper)
    return wrap(
      <div className="house-actions">
        <Text as="p">
          {t(
            "To do this from here, turn on Control Room buttons once: on the server, in the HouseOS folder, run",
          )}
        </Text>
        <CopyCommand command="./houseos.sh buttons on" />
        <Text as="p" style="body-s" tone="muted">
          {t("Or run it there yourself:")}
        </Text>
        {Object.keys(COMMANDS)
          .filter(shown)
          .map((a) => (
            <CopyCommand key={a} command={COMMANDS[a]} />
          ))}
      </div>,
    );
  const buttons = [
    shown("update") && about.version !== "zip" && "update",
    shown("backup") && "backup",
    shown("gpu-on") && about.gpu_available === "yes" && (about.gpu === "on" ? "gpu-off" : "gpu-on"),
    shown("own-address") && (about.own_address ? "own-address-off" : "own-address"),
  ].filter(Boolean) as string[];
  const last = (d.tasks || [])
    .filter((x: Obj) => x.state !== "running" && (!only || only.includes(x.action)))
    .slice(0, 1);
  return wrap(
    <div className="house-actions">
      {!only && (
        <Text as="p">
          {about.version === "zip"
            ? t(
                "Installed from a ZIP: to update, unpack the new one over this folder, then run ./houseos.sh update on the server.",
              )
            : d.available
              ? t("HouseOS {latest} is ready (you have {current}).")
                  .replace("{latest}", d.available[1])
                  .replace("{current}", d.available[0] || "?")
              : d.checked
                ? t("HouseOS is up to date.")
                : t("Checking for a new version…")}
          {about.gpu_available === "yes" && (
            <>
              {" "}
              {about.gpu === "on"
                ? t("Voice typing runs on the graphics card.")
                : t("Voice typing runs on the processor.")}
            </>
          )}
          {about.own_address && (
            <>
              {" "}
              {t("HouseOS has its own address on the network:")}{" "}
              <strong>{about.own_address}</strong>
            </>
          )}
        </Text>
      )}
      <Cluster>
        {buttons.map((a) => (
          <Button
            key={a}
            variant={a === "update" && d.available ? "primary" : "secondary"}
            disabled={!!running}
            onClick={() => setOpen(a)}
          >
            {NAMES[a]()}
          </Button>
        ))}
        <Button
          variant="quiet"
          icon="refresh"
          busy={checking}
          disabled={!!running}
          onClick={async () => {
            setChecking(true);
            try {
              await api("/admin/house-actions/check", "POST");
              setTimeout(() => void s.reload().finally(() => setChecking(false)), 8000);
            } catch {
              setChecking(false);
            }
          }}
        >
          {checking ? t("Looking…") : t("Check for updates")}
        </Button>
      </Cluster>
      {shown("update") && about.version !== "zip" && (
        <Switch
          checked={!!d.auto}
          label={t("Update by itself at night")}
          hint={t(
            "Between 3 and 5 am, only when nothing is playing. Either way, admins get a note in their inbox when a new version is out, and Nox can update on request: “update HouseOS”.",
          )}
          onChange={async (auto) => {
            s.setData({ ...d, auto }); // at once; the house's answer follows
            await api("/admin/house-actions/updates", "PUT", { auto }).finally(s.reload);
          }}
        />
      )}
      {running ? (
        <Notice tone="info">
          {NAMES[running.action]?.() || running.action}:{" "}
          {t(
            "in progress. HouseOS may disappear for a few minutes; this page comes back by itself.",
          )}
        </Notice>
      ) : (
        <Problem error={s.error} />
      )}
      {last.map((x: Obj) => (
        <Disclosure
          key={x.id}
          summary={
            <>
              {NAMES[x.action]?.() || message(x.action)}:{" "}
              <Status tone={x.state === "done" ? "success" : "danger"}>
                {x.state === "done" ? t("done") : t("failed")}
              </Status>
              {x.message && <> · {message(x.message)}</>}
            </>
          }
        >
          <pre className="setup-log">{x.log}</pre>
        </Disclosure>
      ))}
      {open && (
        <Sheet title={NAMES[open]()} place="center" onClose={() => setOpen("")}>
          <Form
            submit={NAMES[open]()}
            onSubmit={async (form) => {
              const prepared = await api("/admin/house-actions/" + open + "/prepare", "POST", {
                address: form.get("address") || undefined,
              });
              await api("/admin/house-actions/confirm/" + prepared.confirmation_id, "POST");
              setOpen("");
              await s.reload();
            }}
          >
            <Text as="p">{t(d.effects?.[open] || "")}</Text>
            {open === "own-address" && (
              <Field
                label={t("Address for HouseOS")}
                hint={t(
                  "A free address on your network, outside your router's automatic range, such as 192.168.1.250.",
                )}
              >
                <Input name="address" required inputMode="decimal" placeholder="192.168.1.250" />
              </Field>
            )}
          </Form>
        </Sheet>
      )}
    </div>,
  );
}
