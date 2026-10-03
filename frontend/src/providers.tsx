import { useEffect, useRef, useState, type ReactNode } from "react";
import { api, items, number, useData, type Obj } from "./api";
import {
  Button,
  Checkbox,
  Cluster,
  ConfirmSheet,
  Disclosure,
  Field,
  Form,
  Grid,
  Input,
  LinkButton,
  List,
  ListRow,
  Notice,
  Problem,
  ReviewDetails,
  SearchInput,
  SecretInput,
  Section,
  Select,
  Sheet,
  Stack,
  Status,
  Surface,
  Text,
  toast,
} from "./design";
import { t } from "./i18n";
import "./providers.css";

// AI connections, in the order Nox falls back to when no assistant model is assigned.
export const AI_PROVIDERS = ["openrouter", "compatible", "anthropic", "openai"];
const NAMES: Record<string, string> = {
  openrouter: "OpenRouter",
  compatible: "Self-hosted",
  anthropic: "Anthropic",
  openai: "OpenAI",
  codex: "ChatGPT subscription",
  claude_code: "Claude subscription",
};
const providerName = (provider: string, mode = "api") =>
  t(NAMES[mode === "api" ? provider : mode] || provider);
const CARDS = [
  {
    title: "ChatGPT subscription",
    text: "Sign in with your ChatGPT plan. It stays personal to you.",
    providers: ["openai"],
    mode: "codex",
  },
  {
    title: "Claude subscription",
    text: "Sign in with your Claude plan. It stays personal to you.",
    providers: ["anthropic"],
    mode: "claude_code",
  },
  {
    title: "OpenRouter",
    text: "One key for many models, paid per use.",
    providers: ["openrouter"],
    mode: "api",
  },
  {
    title: "API key (OpenAI or Anthropic)",
    text: "A key from your OpenAI or Anthropic developer account.",
    providers: ["openai", "anthropic"],
    mode: "api",
  },
  {
    title: "Self-hosted or other OpenAI-compatible",
    text: "A model on your own computer (Ollama, LM Studio, vLLM…): free and private. Or another service with an OpenAI-compatible API.",
    providers: ["compatible"],
    mode: "api",
  },
];
type Card = (typeof CARDS)[number];
const GROUPS: [string, Card[]][] = [
  ["Your own subscription", CARDS.filter((card) => card.mode !== "api")],
  ["For the whole house", CARDS.filter((card) => card.mode === "api")],
];
const PRESETS = [
  ["Ollama", "http://host.docker.internal:11434/v1"],
  ["LM Studio", "http://host.docker.internal:1234/v1"],
  ["vLLM", "http://host.docker.internal:8000/v1"],
];
const connection = (card: Card, rows: Obj[]) =>
  rows.find(
    (r) =>
      card.providers.includes(r.name) && r.enabled && (r.config?.auth_mode || "api") === card.mode,
  );

/** Small print under a control or a card. */
const Fine = ({ children }: { children: ReactNode }) => (
  <Text as="p" style="body-s" tone="muted">
    {children}
  </Text>
);

/** Control Room → AI: five ways to connect Nox, each one input or the official sign-in. */
export function AiConnections() {
  const integrations = useData("/admin/integrations"),
    assistants = useData("/admin/assistants");
  const [open, setOpen] = useState<Card | null>(null),
    [advanced, setAdvanced] = useState<Obj | null>(null);
  const rows = items(integrations.data).filter((r) => AI_PROVIDERS.includes(r.name));
  const nox = items(assistants.data).find((i) => i.purpose === "general");
  const mode = (assistants.data?.connections || []).find(
    (c: Obj) => c.provider === nox?.provider,
  )?.auth_mode;
  const reload = () => {
    integrations.reload();
    assistants.reload();
  };
  return (
    <>
      <Section
        title={
          nox?.ready
            ? `${t("Nox uses")} ${providerName(nox.provider, mode)} · ${nox.model}`
            : t("Nox isn't connected yet")
        }
        actions={
          nox?.ready && nox.tested ? <Status tone="success">{t("tested")}</Status> : undefined
        }
      >
        <Problem error={integrations.error} onRetry={integrations.reload} />
        {/* Personal sign-ins, then what the whole house can use: two full rows, no empty slot. */}
        {GROUPS.map(([label, cards]) => (
          <div className="providers-group" key={label}>
            <Text as="h3" style="label" tone="muted">
              {t(label)}
            </Text>
            <div className="providers-cards">
              {cards.map((card) => (
                <ProviderCard
                  key={card.title}
                  card={card}
                  row={connection(card, rows)}
                  onOpen={() => setOpen(card)}
                />
              ))}
            </div>
          </div>
        ))}
      </Section>
      {/* In sight, not folded away: each assistant (everyday Nox, setup, My space) has its own. */}
      <AssistantAssignments />
      {open && (
        <Sheet title={t(open.title)} place="center" onClose={() => setOpen(null)}>
          <Stack>
            {open.mode === "api" ? (
              <KeyConnect card={open} row={connection(open, rows)} onDone={reload} />
            ) : (
              <SubscriptionConnect card={open} onDone={reload} />
            )}
            {connection(open, rows) && (
              <Cluster>
                <Button
                  variant="quiet"
                  icon="settings"
                  onClick={() => {
                    setAdvanced(connection(open, rows)!);
                    setOpen(null);
                  }}
                >
                  {t("Advanced settings")}
                </Button>
              </Cluster>
            )}
          </Stack>
        </Sheet>
      )}
      {advanced && (
        <ProviderEditor row={advanced} onDone={reload} onClose={() => setAdvanced(null)} />
      )}
    </>
  );
}

/** One way to connect: what it is, then its state and its button at the foot, level with the
 *  cards beside it. A subscription whose sign-in helper isn't installed says so here. */
function ProviderCard({ card, row, onOpen }: { card: Card; row?: Obj; onOpen: () => void }) {
  const native = useData(
    card.mode === "api" ? null : "/admin/providers/" + card.providers[0] + "/native/status",
  );
  const unavailable = !row && native.data?.status === "unavailable";
  return (
    <Surface as="article" material="raised" className="providers-card">
      <Text as="h4" style="title-s">
        {t(card.title)}
      </Text>
      <Fine>{t(card.text)}</Fine>
      <div className="providers-card__foot">
        {row ? (
          <Status tone="success">
            {`${t("Connected")} · ${providerName(row.name)} · ${row.config?.model || ""}`}
          </Status>
        ) : unavailable ? (
          <Status tone="warning">{t("Not available on this install")}</Status>
        ) : (
          <Status>{t("Not connected")}</Status>
        )}
        <Cluster>
          <Button size="s" disabled={unavailable} onClick={onOpen}>
            {t(row ? "Manage" : "Connect")}
          </Button>
        </Cluster>
      </div>
    </Surface>
  );
}

function Outcome({ result }: { result: Obj }) {
  const passed = !result.tested || result.tested === "verified";
  return (
    <Notice tone={passed ? "success" : "warning"}>
      {t("Connected")} · {result.model}
      {result.tested === "verified"
        ? " · " + t("tested")
        : result.test_code === "PROVIDER_TIMEOUT"
          ? " · " + t("The model was still loading. Press Connect again.")
          : result.tested
            ? " · " +
              t("The quick tool test did not pass. Choose another model in Advanced settings.") +
              (result.test_detail ? " " + t("The provider said:") + " " + result.test_detail : "")
            : ""}
    </Notice>
  );
}

function KeyConnect({ card, row, onDone }: { card: Card; row?: Obj; onDone: () => void }) {
  const hosted = card.providers[0] === "compatible";
  const viaOpenRouter = card.providers[0] === "openrouter";
  const [url, setUrl] = useState(hosted ? row?.config?.base_url || "" : ""),
    [result, setResult] = useState<Obj | null>(null);
  return (
    <>
      <Form
        submit={t("Connect")}
        onSubmit={async (f) => {
          const key = String(f.get("key") || "").trim();
          // One box for both kinds of key: Anthropic keys start with sk-ant-.
          const provider =
            card.providers.length === 1
              ? card.providers[0]
              : key
                ? key.startsWith("sk-ant-")
                  ? "anthropic"
                  : "openai"
                : row!.name;
          setResult(null);
          setResult(
            await api("/admin/providers/" + provider + "/connect", "POST", {
              ...(key ? { api_key: key } : {}),
              ...(hosted ? { base_url: url } : {}),
            }),
          );
          onDone();
        }}
      >
        {hosted && (
          <>
            <Cluster>
              {PRESETS.map(([name, preset]) => (
                <Button size="s" key={name} pressed={url === preset} onClick={() => setUrl(preset)}>
                  {name}
                </Button>
              ))}
            </Cluster>
            <Field
              label={t("Server address")}
              hint={t(
                "host.docker.internal reaches the computer running HouseOS in Docker. Without Docker, use 127.0.0.1 instead.",
              )}
            >
              <Input
                type="url"
                required
                value={url}
                placeholder="http://host.docker.internal:11434/v1"
                onChange={(e) => setUrl(e.target.value)}
              />
            </Field>
            <Fine>
              {t("Other OpenAI-compatible services work too, for example:")}{" "}
              <code>https://api.groq.com/openai/v1</code>, <code>https://api.mistral.ai/v1</code>,{" "}
              <code>https://generativelanguage.googleapis.com/v1beta/openai</code>
            </Fine>
          </>
        )}
        <Field
          label={t(
            hosted
              ? "API key (only if your server asks for one)"
              : viaOpenRouter
                ? "OpenRouter API key"
                : "OpenAI or Anthropic API key",
          )}
          hint={
            !hosted && (
              <>
                {t(
                  viaOpenRouter
                    ? "Create a key at openrouter.ai/keys."
                    : "Create a key at platform.openai.com or console.anthropic.com. HouseOS recognises which one it is.",
                )}
                {row && " " + t("Leave empty to keep the saved key.")}
              </>
            )
          }
        >
          <SecretInput
            name="key"
            required={!hosted && !row}
            placeholder={row ? t("Saved. Leave empty to keep it") : hosted ? "" : "sk-…"}
          />
        </Field>
      </Form>
      {result && <Outcome result={result} />}
    </>
  );
}

function SubscriptionConnect({ card, onDone }: { card: Card; onDone: () => void }) {
  const provider = card.providers[0],
    codex = card.mode === "codex";
  const [login, setLogin] = useState<Obj | null>(null),
    [pasting, setPasting] = useState(false),
    [signingOut, setSigningOut] = useState(false),
    [result, setResult] = useState<Obj | null>(null),
    [error, setError] = useState("");
  const base = "/admin/providers/" + provider;
  const state = useData(base + "/native/status", { interval: login && codex ? 3000 : 0 });
  const connecting = useRef(false);
  async function act(action: () => Promise<unknown>) {
    setError("");
    try {
      await action();
    } catch (e) {
      setError((e as Error).message);
    }
  }
  const connect = () =>
    act(async () => {
      setResult(await api(base + "/connect", "POST", { auth_mode: card.mode }));
      setLogin(null);
      onDone();
    });
  // The ChatGPT device sign-in finishes on OpenAI's page; connect as soon as it reports success.
  useEffect(() => {
    if (codex && login && state.data?.logged_in && !connecting.current) {
      connecting.current = true;
      void connect().finally(() => (connecting.current = false));
    }
  }, [login, state.data?.logged_in]);
  if (state.data?.status === "unavailable")
    return (
      <Notice tone="warning" title={t("Not available on this install.")}>
        {t(
          "Its sign-in helper is not installed here, so use an API key, OpenRouter or a self-hosted model instead.",
        )}
      </Notice>
    );
  return (
    <Stack>
      <Fine>
        {t(
          codex
            ? "Sign in on OpenAI's page with the code shown here. HouseOS never sees your password."
            : "Sign in on Claude's page (Google sign-in works), then paste the code it shows. HouseOS never sees your password.",
        )}
      </Fine>
      <Problem error={error || state.error} />
      <Cluster>
        <Fine>
          {(state.data?.version
            ? (codex ? "Codex " : "Claude Code ") + state.data.version + " · "
            : "") + t("Updates itself daily: new models need recent versions.")}
        </Fine>
        <Button
          variant="quiet"
          icon="refresh"
          onClick={() =>
            act(async () => {
              await api("/admin/providers/helpers/update", "POST");
              toast(t("Updating the sign-in helpers: it takes a few minutes."));
            })
          }
        >
          {t("Update now")}
        </Button>
      </Cluster>
      {/* The result sits right under the button that produced it, in sight without scrolling. */}
      {result && <Outcome result={result} />}
      {state.data?.logged_in && !login ? (
        <Cluster>
          <Button variant="primary" onClick={connect}>
            {t("Use this subscription for Nox")}
          </Button>
          <Button variant="quiet" onClick={() => setSigningOut(true)}>
            {t("Sign out")}
          </Button>
        </Cluster>
      ) : (
        !login && (
          <Cluster>
            <Button
              variant="primary"
              onClick={() => act(async () => setLogin(await api(base + "/native/login", "POST")))}
            >
              {t(codex ? "Sign in with ChatGPT" : "Sign in with Claude")}
            </Button>
          </Cluster>
        )
      )}
      {login?.verification_url && (
        <ol className="providers-steps">
          <li>
            <LinkButton
              variant="primary"
              icon="link"
              href={login.verification_url}
              target="_blank"
              rel="noreferrer"
            >
              {t("Open the official sign-in page")}
            </LinkButton>
          </li>
          <li>
            {codex ? (
              <>
                {t("Enter this code there:")} <strong>{login.user_code}</strong>{" "}
                {t("This page continues by itself.")}
              </>
            ) : (
              t("Copy the code shown after signing in and paste it below.")
            )}
          </li>
        </ol>
      )}
      {!codex && (login || pasting) && (
        <Form
          submit={t("Finish sign-in")}
          onSubmit={async (f) => {
            const done = await api<Obj>(base + "/native/login/code", "POST", {
              code: f.get("code"),
            });
            if (done?.status === "code_rejected") {
              // Claude refused it (expired, or from an earlier page): a fresh page is ready.
              setLogin(done);
              throw new Error(
                t(
                  "Claude didn't accept that code (it expires quickly, and only the newest page's code works). Open the sign-in page again below, then paste the new code.",
                ),
              );
            }
            await state.reload();
            await connect();
          }}
        >
          <Field label={t(login ? "Code from the sign-in page" : "Token from claude setup-token")}>
            <SecretInput name="code" required />
          </Field>
        </Form>
      )}
      {!codex && !login && !pasting && !state.data?.logged_in && (
        <Cluster>
          <Button variant="quiet" onClick={() => setPasting(true)}>
            {t("Already ran claude setup-token? Paste its token")}
          </Button>
        </Cluster>
      )}
      {login && (
        <Cluster>
          <Button
            variant="quiet"
            onClick={() =>
              act(async () => {
                await api(base + "/native/login/cancel", "POST");
                setLogin(null);
              })
            }
          >
            {t("Cancel sign-in")}
          </Button>
        </Cluster>
      )}
      {signingOut && (
        <ConfirmSheet
          title={t("Sign this subscription out of HouseOS?")}
          confirm={t("Sign out")}
          danger
          onClose={() => setSigningOut(false)}
          onConfirm={() =>
            act(async () => {
              await api(base + "/native/logout", "POST");
              await state.reload();
              onDone();
            })
          }
        >
          <Text>{t(card.title)}</Text>
        </ConfirmSheet>
      )}
    </Stack>
  );
}

function ProviderEditor({
  row,
  onDone,
  onClose,
}: {
  row: Obj;
  onDone: () => void;
  onClose: () => void;
}) {
  const mode = row.config?.auth_mode || "api";
  const [removeKey, setRemoveKey] = useState(false);
  const [secret, setSecret] = useState(""),
    [query, setQuery] = useState(""),
    [model, setModel] = useState(row.config?.model || "");
  const [error, setError] = useState(""),
    [refreshing, setRefreshing] = useState(false),
    [toolsOnly, setToolsOnly] = useState(row.name === "openrouter");
  const catalog = useData("/admin/providers/" + row.name + "/models");
  const native = mode !== "api",
    counted = native || row.name === "compatible";
  const available = items(catalog.data).filter(
    () => !catalog.data?.auth_mode || catalog.data.auth_mode === mode,
  );
  const filtered = available.filter(
    (m) =>
      (!toolsOnly || m.tool_support === "declared") &&
      (m.id + " " + m.name).toLowerCase().includes(query.toLowerCase()),
  );
  const selected = available.find((m) => m.id === model);
  async function refresh() {
    setRefreshing(true);
    try {
      catalog.setData(
        await api("/admin/providers/" + row.name + "/models/refresh", "POST", {
          ...(secret ? { api_key: secret } : {}),
          auth_mode: mode,
        }),
      );
      setError("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setRefreshing(false);
    }
  }
  return (
    <Sheet
      title={providerName(row.name, mode) + " · " + t("connection")}
      place="center"
      onClose={onClose}
    >
      <Stack>
        <Problem error={error || catalog.error} />
        <Form
          submit={t("Save connection and model")}
          onSubmit={async (f) => {
            const config: Obj = {
              ...row.config,
              auth_mode: mode,
              model,
              max_output_tokens: Number(f.get("max_output_tokens") || 800),
            };
            if (row.name === "openrouter") {
              const effort = f.get("reasoning_effort");
              if (effort) config.reasoning_effort = effort;
              else delete config.reasoning_effort;
            }
            if (f.has("requests")) {
              config.daily_request_limit = Number(f.get("requests") || 100);
              config.user_daily_request_limit = config.daily_request_limit;
            }
            if (!counted) {
              config.daily_budget_microusd = Math.round(Number(f.get("house_budget")) * 1e6);
              config.user_daily_budget_microusd = Math.round(Number(f.get("user_budget")) * 1e6);
              if (row.name === "openrouter" && selected?.pricing)
                Object.assign(config, selected.pricing);
              for (const k of [
                "input_microusd_per_million",
                "output_microusd_per_million",
                "cached_input_microusd_per_million",
                "cache_write_microusd_per_million",
              ]) {
                if (!f.has(k)) continue;
                if (f.get(k) !== "") config[k] = Math.ceil(Number(f.get(k)) * 1e6);
                else delete config[k];
              }
            }
            await api("/admin/integrations/" + row.name, "PUT", {
              enabled: f.get("enabled") === "on",
              config,
              ...(!native && (secret || removeKey) ? { secret: removeKey ? "" : secret } : {}),
            });
            onDone();
            onClose();
          }}
        >
          {!native && (
            <Field
              label={t(
                row.has_secret
                  ? "API key · leave empty to keep saved key"
                  : row.name === "compatible"
                    ? "API key (optional)"
                    : "API key",
              )}
            >
              <SecretInput value={secret} onChange={(e) => setSecret(e.target.value)} />
            </Field>
          )}
          {!native && row.has_secret && (
            <Checkbox
              checked={removeKey}
              onChange={(e) => setRemoveKey(e.target.checked)}
              label={t("Remove saved API key when saving")}
            />
          )}
          {native && row.name === "anthropic" && (
            <Fine>
              {t(
                "Claude Code offers its native model aliases; account availability is checked by the native client when used.",
              )}
            </Fine>
          )}
          <Cluster>
            <Button size="s" icon="refresh" busy={refreshing} onClick={refresh}>
              {t(refreshing ? "Refreshing models…" : "Refresh model list")}
            </Button>
            <Text style="caption" tone="muted">
              {available.length} {t("models · refresh keeps your selection")}
            </Text>
          </Cluster>
          <SearchInput
            label={t("Search models")}
            value={query}
            onChange={setQuery}
            placeholder={t("Type a model or provider name…")}
          />
          {row.name === "openrouter" && (
            <Checkbox
              checked={toolsOnly}
              onChange={(e) => setToolsOnly(e.target.checked)}
              label={t("Show models declaring tool support")}
            />
          )}
          <Field
            label={t("Connection test model")}
            hint={t(
              "This connection model is used for capability checks. Assign Home and My space models in Assistant models above.",
            )}
          >
            <Select value={model} onChange={(e) => setModel(e.target.value)}>
              <option value="">{t("Select a model")}</option>
              {model && !filtered.some((m) => m.id === model) && (
                <option value={model}>
                  {model} · {t("current selection")}
                </option>
              )}
              {filtered.slice(0, 250).map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name} · {m.id}
                </option>
              ))}
            </Select>
          </Field>
          {filtered.length > 250 && (
            <Fine>
              {filtered.length}{" "}
              {t("matches; type more to narrow the list. Every catalog model is searchable.")}
            </Fine>
          )}
          {!available.length && (
            <Fine>{t("Connect, then refresh to choose a model. No model URL is needed.")}</Fine>
          )}
          {selected && (
            <Fine>
              {t(
                selected.tool_support === "declared"
                  ? "Tool support declared"
                  : "Tool support needs a capability check",
              )}
              {selected.context_length
                ? ` · ${number(selected.context_length)} ${t("context tokens")}`
                : ""}
              {selected.pricing?.input_microusd_per_million !== undefined
                ? ` · $${selected.pricing.input_microusd_per_million / 1e6} ${t("input")} / $${selected.pricing.output_microusd_per_million / 1e6} ${t("output per million tokens")}`
                : ""}
            </Fine>
          )}
          {row.name === "openrouter" && (
            <Field
              label={t("Reasoning effort")}
              hint={t(
                "Applied to reasoning-capable models. Unsupported settings are rejected rather than silently ignored.",
              )}
            >
              <Select name="reasoning_effort" defaultValue={row.config?.reasoning_effort || ""}>
                <option value="">{t("Model default")}</option>
                <option value="low">{t("Low · quick household tasks")}</option>
                <option value="medium">{t("Medium")}</option>
                <option value="high">{t("High")}</option>
              </Select>
            </Field>
          )}
          <Checkbox
            name="enabled"
            defaultChecked={row.enabled || !row.configured}
            label={t("Enable this connection")}
          />
          <Disclosure summary={t("Usage limits and advanced options")}>
            <Stack>
              {row.name !== "openrouter" && (
                <Field label={t("Daily requests")}>
                  <Input
                    name="requests"
                    type="number"
                    min="1"
                    max="10000"
                    defaultValue={row.config?.daily_request_limit || 100}
                  />
                </Field>
              )}
              {native && (
                <Fine>
                  {t(
                    "This is your personal native account, not a shared household API key. Provider subscription limits also apply; no invented API dollar cost is shown.",
                  )}
                </Fine>
              )}
              {!counted && (
                <>
                  <Field label={t("Daily household budget · USD")}>
                    <Input
                      name="house_budget"
                      type="number"
                      min="0"
                      step="0.01"
                      defaultValue={(row.config?.daily_budget_microusd ?? 1000000) / 1e6}
                    />
                  </Field>
                  <Field label={t("Daily per-person budget · USD")}>
                    <Input
                      name="user_budget"
                      type="number"
                      min="0"
                      step="0.01"
                      defaultValue={(row.config?.user_daily_budget_microusd ?? 250000) / 1e6}
                    />
                  </Field>
                  {row.name === "openrouter" ? (
                    <Fine>
                      {t(
                        "Published model pricing is filled automatically when saved. Default limits are $1/day household and $0.25/person; zero disables paid calls.",
                      )}
                    </Fine>
                  ) : (
                    <>
                      <Fine>
                        {t(
                          "Optional. Without prices, the daily request limit applies instead of dollar budgets.",
                        )}
                      </Fine>
                      {[
                        ["input_microusd_per_million", "Input"],
                        ["output_microusd_per_million", "Output"],
                        ["cached_input_microusd_per_million", "Cache read"],
                        ["cache_write_microusd_per_million", "Cache write"],
                      ].map(([k, l]) => (
                        <Field key={k} label={t(l) + " · " + t("USD per million tokens")}>
                          <Input
                            name={k}
                            type="number"
                            min="0"
                            step="0.000001"
                            defaultValue={row.config?.[k] === undefined ? "" : row.config[k] / 1e6}
                          />
                        </Field>
                      ))}
                    </>
                  )}
                </>
              )}
              <Field label={t("Maximum answer tokens (API)")}>
                <Input
                  name="max_output_tokens"
                  type="number"
                  min="1"
                  max="4096"
                  defaultValue={row.config?.max_output_tokens || 800}
                />
              </Field>
            </Stack>
          </Disclosure>
        </Form>
        <ProviderProbe name={row.name} />
      </Stack>
    </Sheet>
  );
}

function ProviderProbe({ name }: { name: string }) {
  const [preview, setPreview] = useState<Obj | null>(null),
    [result, setResult] = useState<Obj | null>(null);
  return (
    <Disclosure summary={t("Verify structured tool support")}>
      <Stack>
        <Form
          submit={t("Review one capability test")}
          onSubmit={async () => {
            setPreview(await api("/admin/providers/" + name + "/probe/prepare", "POST", {}));
            setResult(null);
          }}
        >
          <Text as="p">
            {t(
              "Save your connection first. This optional synthetic request uses its normal API budget or native subscription allowance.",
            )}
          </Text>
        </Form>
        {preview && (
          <>
            <ReviewDetails value={preview.preview} />
            <Form
              submit={t("Confirm this test")}
              onSubmit={async () => {
                setResult(
                  await api("/admin/providers/probe/confirm/" + preview.confirmation_id, "POST"),
                );
                setPreview(null);
              }}
            >
              <Text as="p">{t("No resident conversation content is sent.")}</Text>
            </Form>
          </>
        )}
        {result && <ReviewDetails value={result} />}
      </Stack>
    </Disclosure>
  );
}

function AssistantAssignments() {
  const state = useData("/admin/assistants");
  const connections: Obj[] = state.data?.connections || [];
  // Arriving from My space's "Change the My space model" link: bring this section into view.
  useEffect(() => {
    if (state.data && location.hash === "#assistant-models")
      document.getElementById("assistant-models")?.scrollIntoView({ block: "start" });
  }, [!!state.data]);
  const modeOf = (provider: string) =>
    connections.find((c) => c.provider === provider)?.auth_mode || "api";
  return (
    <Section
      id="assistant-models"
      title={t("Which model each assistant uses")}
      lead={t(
        "Everyday Nox, setup mode, My space and the theme studio each have their own setting.",
      )}
    >
      <Stack>
        <ol className="providers-steps">
          <li>
            {t(
              "Connect at least one AI above: a ChatGPT or Claude sign-in (your subscription, usable only by you), an API key the whole house can use (OpenRouter, OpenAI, Anthropic), or your own model.",
            )}
          </li>
          <li>
            {t(
              "For each assistant below, choose the connection, the exact model and how hard it thinks. Residents never have to choose anything.",
            )}
          </li>
        </ol>
        <Notice>
          {t(
            "Everyday Nox answers often: a fast, inexpensive model at low effort. Setup mode and the theme studio are used rarely: your smartest model at medium.",
          )}
        </Notice>
        <Problem error={state.error} onRetry={state.reload} />
        <Section level={3} title={t("Right now")}>
          <List label={t("Right now")}>
            {items(state.data).map((row) => (
              <ListRow
                key={row.purpose}
                title={ROLES[row.purpose]?.()[0] || row.purpose}
                detail={
                  <>
                    {providerName(row.provider, modeOf(row.provider))} ·{" "}
                    <code>{row.model || t("none yet")}</code> ·{" "}
                    {t(row.reasoning_effort ? EFFORTS[row.reasoning_effort] : "Model default")}
                  </>
                }
                status={
                  !row.ready
                    ? { tone: "warning", text: t("not ready") }
                    : row.tested
                      ? { tone: "success", text: t("tested") }
                      : { tone: "info", text: t("ready") }
                }
              />
            ))}
          </List>
        </Section>
        <Grid min="18rem">
          {items(state.data).map((row) => (
            <AssignmentEditor
              key={row.purpose}
              row={row}
              connections={connections}
              recent={state.data?.recent || []}
              saved={state.reload}
            />
          ))}
        </Grid>
      </Stack>
    </Section>
  );
}

const EFFORTS: Record<string, string> = { low: "Low", medium: "Medium", high: "High" };

/** Each assistant's title and what it is for. */
const ROLES: Record<string, () => [string, string]> = {
  general: () => [
    t("Household assistant"),
    t("Home and Chats: tasks, music, movies and household tools."),
  ],
  personal_space: () => [
    t("My space setup assistant"),
    t(
      "Only personal news, subreddit and image-feed setup. Daily refreshes use code, not this model.",
    ),
  ],
  setup: () => [
    t("House setup assistant (admins)"),
    t("Nox's setup mode, for administrators. A smarter model helps most here."),
  ],
  themes: () => [
    t("Theme studio"),
    t(
      "Designs themes with the people who live here. Recommended: Claude (subscription) · Claude Opus 5.5 · medium; it looks at pictures and searches the web.",
    ),
  ],
};

function AssignmentEditor({
  row,
  connections,
  recent,
  saved,
}: {
  row: Obj;
  connections: Obj[];
  recent: Obj[];
  saved: () => void;
}) {
  const [provider, setProvider] = useState(row.provider),
    [model, setModel] = useState(row.model || ""),
    [effort, setEffort] = useState(row.reasoning_effort || ""),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [check, setCheck] = useState<Obj | null>(null),
    [refreshing, setRefreshing] = useState(false);
  const catalog = useData("/admin/providers/" + provider + "/models");
  const connection = connections.find((c) => c.provider === provider);
  const models = items(catalog.data).filter(
    (m) =>
      (provider !== "openrouter" || m.tool_support === "declared") &&
      (!catalog.data?.auth_mode || catalog.data.auth_mode === connection?.auth_mode),
  );
  const used = recent
    .filter((r) => r.provider === provider)
    .map((r) => r.model)
    .filter((id: string) => !models.some((m) => m.id === id));
  const selected = models.find((m) => m.id === model),
    native = connection?.auth_mode === "codex" || connection?.auth_mode === "claude_code",
    reasoning =
      native ||
      (provider === "openrouter" && selected?.supported_parameters?.includes("reasoning"));
  const [title, purpose] = ROLES[row.purpose]?.() || [row.purpose, ""];
  return (
    <Surface as="article" material="raised" className="providers-card">
      <Text as="h3" style="title-s">
        {title}
      </Text>
      <Fine>{purpose}</Fine>
      <Problem error={error || catalog.error} />
      <Form
        submit={t("Save and test")}
        onSubmit={async () => {
          setError("");
          setNotice("");
          setCheck(null);
          try {
            await api("/admin/assistants/" + row.purpose, "PUT", {
              provider,
              model: model.trim(),
              reasoning_effort: reasoning && effort ? effort : null,
            });
          } catch (e) {
            setError((e as Error).message);
            return;
          }
          saved();
          // Saved; then one real short round with this assistant's own instructions and tools.
          setNotice(t("Saved. Testing it with one short real request…"));
          try {
            setCheck(await api<Obj>("/admin/assistants/" + row.purpose + "/test", "POST"));
            setNotice("");
          } catch (e) {
            setNotice(t("Saved."));
            setCheck({ status: "failed", message: (e as Error).message });
          }
        }}
      >
        <Field label={t("Provider")}>
          <Select
            value={provider}
            onChange={(e) => {
              setProvider(e.target.value);
              setModel("");
              setEffort("");
              setNotice("");
              setCheck(null);
            }}
          >
            {connections.map((c) => (
              <option key={c.provider} value={c.provider} disabled={!c.enabled}>
                {providerName(c.provider, c.auth_mode)}
                {!c.enabled ? " · " + t("not connected") : ""}
              </option>
            ))}
          </Select>
        </Field>
        <Cluster>
          <Button
            size="s"
            icon="refresh"
            busy={refreshing}
            disabled={!connection?.enabled}
            onClick={async () => {
              setRefreshing(true);
              try {
                catalog.setData(
                  await api("/admin/providers/" + provider + "/models/refresh", "POST", {
                    auth_mode: connection?.auth_mode || "api",
                  }),
                );
                setError("");
              } catch (e) {
                setError((e as Error).message);
              } finally {
                setRefreshing(false);
              }
            }}
          >
            {t(refreshing ? "Refreshing…" : "Refresh model list")}
          </Button>
        </Cluster>
        <Field
          label={t("Model")}
          hint={t(
            "Pick a suggestion or type the exact model id. Refresh the list if a new model is missing.",
          )}
        >
          <Input
            list={row.purpose + "-models"}
            required
            spellCheck={false}
            autoComplete="off"
            onFocus={(e) => e.target.select()}
            placeholder={t("Search, e.g. opus 5.5 or deepseek…")}
            value={model}
            onChange={(e) => {
              setModel(e.target.value);
              setEffort("");
              setCheck(null);
            }}
          />
        </Field>
        {/* Native suggestions filter as you type; any other exact id may be typed too. */}
        <datalist id={row.purpose + "-models"}>
          {used.map((id: string) => (
            <option value={id} key={"used-" + id} label={t("used recently")} />
          ))}
          {models.map((m) => (
            <option
              value={m.id}
              key={m.id}
              label={
                (recent.some((r) => r.provider === provider && r.model === m.id)
                  ? t("used recently") + " · "
                  : "") + (m.name || m.id)
              }
            />
          ))}
        </datalist>
        {reasoning && (
          <Field label={t("How hard it thinks")}>
            <Select value={effort} onChange={(e) => setEffort(e.target.value)}>
              <option value="">{t(native ? "Low (default)" : "Model default")}</option>
              <option value="low">{t("Low: fastest and cheapest")}</option>
              <option value="medium">{t("Medium: better at tricky requests, slower")}</option>
              <option value="high">{t("High: slowest, for the hardest jobs")}</option>
            </Select>
          </Field>
        )}
        {model && (
          <Text as="p" style="body-s">
            {t("This assistant will use")} <code>{model}</code> ·{" "}
            {providerName(provider, connection?.auth_mode)} ·{" "}
            {t(effort ? EFFORTS[effort] : native ? "Low" : "Model default")}
          </Text>
        )}
        {connection?.auth_mode !== "api" && (
          <Fine>
            {t(
              "This personal sign-in works only for its connected owner. Choose an API connection to serve other residents.",
            )}
          </Fine>
        )}
        <Fine>{t("The provider connection's spending and request limits still apply.")}</Fine>
      </Form>
      {/* Right under "Save and test", in sight when it appears. */}
      {notice && <Notice>{notice}</Notice>}
      {check &&
        (check.status === "verified" ? (
          <Notice tone="success">
            {t("Tested: answered in {n} s with {model}.")
              .replace("{n}", String(check.seconds))
              .replace("{model}", check.model)}
          </Notice>
        ) : (
          <Notice tone="danger">{t("Test failed:") + " " + check.message}</Notice>
        ))}
    </Surface>
  );
}
