import { t, getLanguage } from "./i18n";
import { useEffect, useRef, useState } from "react";
import { api, ApiError, useData } from "./api";
import { IconButton } from "./design";

export type VoiceState = "idle" | "listening" | "transcribing" | "error";
const TYPES = ["audio/webm;codecs=opus", "audio/mp4", "audio/ogg;codecs=opus", "audio/webm"];
const LIMIT_MS = 60000;
// After you have spoken, this much quiet ends the recording and sends what you said.
const SILENCE_MS = 2000;
const SPEAKING = 12; // peak level (0-128) that counts as voice rather than room noise

export const voiceSupported = () =>
  typeof window !== "undefined" &&
  !!navigator.mediaDevices?.getUserMedia &&
  typeof MediaRecorder !== "undefined" &&
  window.isSecureContext;

/** Tap to talk; stop by tapping again or by pausing 2 s. Clear speech, or speech ended by a
 *  pause, is sent at once; anything else lands in the composer to check first. Speech is transcribed on the house computer
 *  and the recording is deleted right after. */
/** Why the microphone can't be used here, in words; "" when it can. */
function voiceBlocker(installed: boolean | undefined, blocked: string) {
  if (typeof window !== "undefined" && !window.isSecureContext)
    return t("Voice needs a secure address: open HouseOS at its https:// address.");
  if (!voiceSupported()) return t("This browser can't record audio.");
  if (installed === false)
    return t("Voice typing isn't installed on this server yet (Control Room → Setup).");
  return blocked;
}

export function VoiceButton({
  onText,
  onState,
  disabled = false,
  blocked = "",
}: {
  onText: (text: string, confident: boolean) => void;
  onState?: (state: VoiceState) => void;
  disabled?: boolean;
  /** A reason the microphone can't be used yet; the button explains it instead of working. */
  blocked?: string;
}) {
  const service = useData<{ available: boolean }>("/assistant/voice/status");
  const reason = voiceBlocker(service.data?.available, blocked);
  const [state, setState] = useState<VoiceState>("idle"),
    [error, setError] = useState("");
  const recorder = useRef<MediaRecorder | null>(null),
    cleanup = useRef<() => void>(() => {}),
    cancelled = useRef(false),
    starting = useRef(false),
    box = useRef<HTMLSpanElement>(null);
  const change = (next: VoiceState) => {
    setState(next);
    onState?.(next);
  };
  // Closing the panel mid-sentence throws the recording away.
  useEffect(
    () => () => {
      cancelled.current = true; // also stops a start() still waiting for permission
      if (recorder.current?.state === "recording") recorder.current.stop();
      cleanup.current();
    },
    [],
  );

  const start = async () => {
    setError("");
    cancelled.current = false;
    let stream: MediaStream;
    starting.current = true;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      starting.current = false;
      setError(t("Allow the microphone to talk to Nox."));
      change("error");
      return;
    }
    starting.current = false;
    // The panel closed (or a second tap came) while the browser was asking.
    if (cancelled.current || recorder.current?.state === "recording") {
      stream.getTracks().forEach((track) => track.stop());
      return;
    }
    const type = TYPES.find((candidate) => MediaRecorder.isTypeSupported(candidate)) || "";
    const media = new MediaRecorder(stream, type ? { mimeType: type } : undefined);
    const chunks: Blob[] = [];
    media.ondataavailable = (e) => e.data.size && chunks.push(e.data);
    // A live level meter shows the microphone is really hearing you.
    const context = new AudioContext();
    const analyser = context.createAnalyser();
    analyser.fftSize = 256;
    context.createMediaStreamSource(stream).connect(analyser);
    const samples = new Uint8Array(analyser.frequencyBinCount);
    let frame = 0,
      spoke = false,
      loud = performance.now(),
      quiet = false;
    const tick = () => {
      analyser.getByteTimeDomainData(samples);
      let peak = 0;
      for (const value of samples) peak = Math.max(peak, Math.abs(value - 128));
      box.current?.style.setProperty("--level", String(Math.min(1, peak / 64)));
      if (peak >= SPEAKING) {
        spoke = true;
        loud = performance.now();
      } else if (spoke && performance.now() - loud > SILENCE_MS && media.state === "recording") {
        quiet = true;
        media.stop();
        return;
      }
      frame = requestAnimationFrame(tick);
    };
    tick();
    const limit = setTimeout(() => media.state === "recording" && media.stop(), LIMIT_MS);
    cleanup.current = () => {
      clearTimeout(limit);
      cancelAnimationFrame(frame);
      stream.getTracks().forEach((track) => track.stop());
      void context.close().catch(() => {});
      box.current?.style.setProperty("--level", "0");
    };
    media.onstop = async () => {
      cleanup.current();
      if (cancelled.current || !chunks.length) return change("idle");
      change("transcribing");
      const blob = new Blob(chunks, { type: media.mimeType || type || "audio/webm" });
      try {
        const language = getLanguage(); // the speech model knows many; unknown ones auto-detect
        // (the browser sends the recording's own type, codecs included; the house reads the kind)
        const data = await api("/assistant/voice?language=" + language, "POST", blob);
        // A pause after speaking means "that's it": the text is sent, like a tap on Send.
        if (data.text) onText(data.text, !!data.confident || quiet);
        else setError(t("Nox did not catch that. Try again, a little closer."));
        change(data.text ? "idle" : "error");
      } catch (e) {
        setError(
          e instanceof ApiError ? e.message : t("Voice is unavailable right now; type instead."),
        );
        change("error");
      }
    };
    recorder.current = media;
    media.start(250);
    change("listening");
  };
  const stop = () => recorder.current?.state === "recording" && recorder.current.stop();
  return (
    <span className="ask-voice" ref={box} data-listening={state === "listening" || undefined}>
      <IconButton
        icon={state === "listening" ? "stop" : "mic"}
        variant={state === "listening" ? "primary" : "secondary"}
        disabled={disabled || state === "transcribing"}
        busy={state === "transcribing"}
        aria-disabled={!!reason || undefined}
        pressed={state === "listening"}
        label={state === "listening" ? t("Stop and use what I said") : t("Talk to Nox")}
        onClick={() => {
          if (reason) return void (setError(reason), change("error"));
          if (state === "listening") stop();
          else if (!starting.current) void start();
        }}
        onKeyDown={(e) => {
          if (e.key === "Escape" && state === "listening") {
            // Only the recording is dropped; the panel stays open.
            e.preventDefault();
            e.stopPropagation();
            cancelled.current = true;
            stop();
          }
        }}
      />
      {state === "listening" && (
        <span className="ask-voice__hint" role="status">
          {t("Listening… pause to send, tap to stop")}
        </span>
      )}
      {state === "transcribing" && (
        <span className="ask-voice__hint" role="status">
          {t("Writing it down…")}
        </span>
      )}
      {error && (
        <span className="ask-voice__hint" data-error="" role="alert">
          {error}
        </span>
      )}
    </span>
  );
}
