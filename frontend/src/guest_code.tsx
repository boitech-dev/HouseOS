// A QR code a guest scans to join without an account: music (Party mode), or music and the TV
// (Watch → Guest code). Its look is in party.css.
import { t } from "./i18n";
import { useEffect, useRef, useState } from "react";
import { qrColours } from "./design/theme";
import { api, useData, items, type Obj } from "./api";
import { Button, Problem, Text } from "./design";
import "./party.css";

/** One single-use code per guest (four hours; the code itself expires in two if unused); a fresh
 *  one once it is used. `tv`: the guest may also pick a film for the TV (preset "screen"). */
export function JoinCode({ tv = false }: { tv?: boolean }) {
  const [invite, setInvite] = useState<Obj | null>(null),
    [qr, setQr] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const invites = useData(invite ? "/auth/invites" : null, {
    interval: (data) => !items(data).find((row) => row.id === invite?.id)?.redeemed && 4000,
  });
  const used = invite && items(invites.data).find((row) => row.id === invite.id)?.redeemed;
  const make = async () => {
    setBusy(true);
    try {
      const created = await api("/auth/invites", "POST", {
        preset: tv ? "screen" : "party",
        expires_hours: 2,
        membership_hours: 4,
      });
      setInvite(created);
      const { default: QRCode } = await import("qrcode");
      setQr(
        await QRCode.toDataURL(location.origin + created.path, {
          width: 240,
          margin: 2,
          color: qrColours(),
        }),
      );
      setError("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  // Opened to show a code: make the first one at once (once, even when effects run twice).
  const started = useRef(false);
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    void make();
  }, []);
  const showing = qr && !used;
  return (
    <section className="party-join" aria-label={t("Join code")}>
      {showing && (
        <img
          className="party-join__qr"
          src={qr}
          alt={t("Join code for one guest")}
          width={240}
          height={240}
        />
      )}
      <div className="party-join__words">
        <Text as="h3" style="title-l">
          {used
            ? t("Welcome in!")
            : tv
              ? t("Scan to add songs and watch on the TV")
              : t("Scan to add your songs")}
        </Text>
        <Text as="p" tone="muted">
          {used
            ? t("That code is used. Make one for the next guest.")
            : tv
              ? t("One guest per code, for four hours: music and the TV, no account.")
              : t("One guest per code, for four hours of music.")}
        </Text>
      </div>
      <Button
        variant={used ? "primary" : "secondary"}
        icon="party"
        busy={busy}
        onClick={() => void make()}
      >
        {t("Code for the next guest")}
      </Button>
      <Problem
        error={error || invites.error}
        onRetry={error ? () => void make() : () => void invites.reload()}
      />
    </section>
  );
}
