import { useState } from "react";
import { api, type Obj } from "./api";
import { Button, ConfirmSheet, Notice, Problem, Section, Text } from "./design";
import { t } from "./i18n";
export function ShutdownHouseOS() {
  const [preview, setPreview] = useState<Obj | null>(null),
    [error, setError] = useState(""),
    [stopping, setStopping] = useState(false);
  return (
    <Section level={3} title={t("Turn HouseOS off")}>
      <Text as="p">
        {t("Stop its background work and players. The desktop HouseOS launcher starts it again.")}
      </Text>
      <Problem error={error} />
      <div>
        <Button
          icon="power"
          disabled={stopping}
          onClick={async () => {
            try {
              setPreview(await api("/admin/services/shutdown/prepare", "POST"));
            } catch (e) {
              setError((e as Error).message);
            }
          }}
        >
          {t("Stop HouseOS…")}
        </Button>
      </div>
      {preview && (
        <ConfirmSheet
          title={t("Stop HouseOS?")}
          confirm={t("Confirm shutdown")}
          danger
          onClose={() => setPreview(null)}
          onConfirm={async () => {
            try {
              setStopping(true);
              await api(`/admin/services/shutdown/confirm/${preview.confirmation_id}`, "POST");
            } catch (e) {
              setStopping(false);
              throw e; // the sheet says what failed, where the person is looking
            }
          }}
        >
          <Text as="p">{preview.preview.effect}</Text>
          <Text as="p">{preview.preview.active_tv}</Text>
        </ConfirmSheet>
      )}
      {stopping && !preview && (
        <Notice tone="info">
          {t(
            "Shutdown accepted. This page will disconnect. You can close this tab; use the desktop launcher to start HouseOS again.",
          )}
        </Notice>
      )}
    </Section>
  );
}
