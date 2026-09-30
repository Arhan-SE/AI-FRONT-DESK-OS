import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import {
  Room,
  RoomEvent,
  Track,
  createAudioAnalyser,
  type RemoteTrack,
  type RemoteParticipant,
} from "livekit-client";
import { StatusDot, type Tone } from "@/components/ui/primitives";
import { Button, InlineError } from "@/components/ui/controls";
import { api, ApiError, type CallPurpose } from "@/lib/api";
import { Phone, PhoneOff, Mic, MicOff, MessageCircle, Wallet, HeartHandshake } from "lucide-react";

/**
 * Reached by clicking a call button on Jobs or Campaigns. Deliberately not
 * inside the dashboard shell: no nav, no other pages — the moment this loads
 * it should feel like picking up a call, not browsing a tool.
 */
const PURPOSE_COPY: Record<CallPurpose, { title: string; blurb: string; icon: typeof Phone }> = {
  review: {
    title: "Quick feedback call",
    blurb: "Apex Climate Care would like to hear how your recent service went.",
    icon: MessageCircle,
  },
  payment: {
    title: "About your invoice",
    blurb: "Apex Climate Care has a quick question about an outstanding payment.",
    icon: Wallet,
  },
  reactivation: {
    title: "We've missed you",
    blurb: "Apex Climate Care wanted to check in — it's been a while.",
    icon: HeartHandshake,
  },
};

type Phase =
  | "idle"
  | "requesting-mic"
  | "connecting"
  | "connected"
  | "agent-joined"
  | "reconnecting"
  | "ended"
  | "failed";

const PHASE: Record<Phase, { label: string; tone: Tone }> = {
  idle: { label: "Ready", tone: "neutral" },
  "requesting-mic": { label: "Requesting microphone…", tone: "warning" },
  connecting: { label: "Connecting…", tone: "warning" },
  connected: { label: "Connected — waiting for the assistant", tone: "warning" },
  "agent-joined": { label: "On the line", tone: "success" },
  reconnecting: { label: "Reconnecting…", tone: "warning" },
  ended: { label: "Call ended", tone: "neutral" },
  failed: { label: "Call failed", tone: "critical" },
};

const VALID_PURPOSES: CallPurpose[] = ["review", "payment", "reactivation"];

export function JoinCallPage() {
  const { purpose, ref } = useParams<{ purpose: string; ref: string }>();
  const valid = VALID_PURPOSES.includes(purpose as CallPurpose) && !!ref;

  const [phase, setPhase] = useState<Phase>("idle");
  const [error, setError] = useState<string | null>(null);
  const [level, setLevel] = useState(0);
  const [muted, setMuted] = useState(false);

  const roomRef = useRef<Room | null>(null);
  const cleanupAnalyser = useRef<(() => void) | null>(null);

  const teardown = useCallback(async () => {
    cleanupAnalyser.current?.();
    cleanupAnalyser.current = null;
    await roomRef.current?.disconnect();
    roomRef.current = null;
    setLevel(0);
    setMuted(false);
  }, []);

  useEffect(() => () => void teardown(), [teardown]);

  const toggleMute = useCallback(async () => {
    const room = roomRef.current;
    if (!room) return;
    const next = !muted;
    await room.localParticipant.setMicrophoneEnabled(!next);
    setMuted(next);
  }, [muted]);

  const start = async () => {
    if (!valid || !ref) return;
    setError(null);
    setPhase("requesting-mic");

    let session;
    try {
      session = await api.joinCall(purpose as CallPurpose, ref);
    } catch (e) {
      setPhase("failed");
      setError(
        e instanceof ApiError
          ? e.status === 404
            ? "This call could not be started — the job, invoice, or customer behind it no longer exists."
            : e.message
          : "Could not reach the server to start the call.",
      );
      return;
    }

    const room = new Room({ adaptiveStream: true, dynacast: true });
    roomRef.current = room;

    room
      .on(RoomEvent.Connected, () => setPhase("connected"))
      .on(RoomEvent.Reconnecting, () => setPhase("reconnecting"))
      .on(RoomEvent.Reconnected, () => setPhase("agent-joined"))
      .on(RoomEvent.Disconnected, () => setPhase((p) => (p === "failed" ? p : "ended")))
      .on(RoomEvent.ParticipantConnected, (p: RemoteParticipant) => {
        if (p.identity.startsWith("agent") || p.isAgent) setPhase("agent-joined");
      })
      .on(RoomEvent.TrackSubscribed, (track: RemoteTrack) => {
        if (track.kind === Track.Kind.Audio) {
          track.attach();
          setPhase("agent-joined");
        }
      });

    try {
      setPhase("connecting");
      await room.connect(session.url, session.token);
      await room.localParticipant.setMicrophoneEnabled(true);

      const mic = room.localParticipant.getTrackPublication(Track.Source.Microphone);
      if (mic?.track) {
        const { calculateVolume, cleanup } = createAudioAnalyser(mic.track as never);
        cleanupAnalyser.current = cleanup;
        const tick = () => {
          if (!roomRef.current) return;
          setLevel(calculateVolume());
          requestAnimationFrame(tick);
        };
        tick();
      }
    } catch (e) {
      setPhase("failed");
      const message = e instanceof Error ? e.message : "";
      setError(
        message.toLowerCase().includes("permission") || message.includes("NotAllowed")
          ? "Microphone permission was refused. Allow it in your browser and try again."
          : "Could not connect. Check your internet connection and try again.",
      );
      await teardown();
    }
  };

  const stop = async () => {
    await teardown();
    setPhase("ended");
  };

  if (!valid) {
    return (
      <CenteredShell>
        <p className="t-page-title mb-2">Nothing to call about</p>
        <p className="t-label">This page was reached without a valid job, invoice, or customer.</p>
      </CenteredShell>
    );
  }

  const copy = PURPOSE_COPY[purpose as CallPurpose];
  const Icon = copy.icon;
  const live = phase === "connected" || phase === "agent-joined" || phase === "reconnecting";
  const meta = PHASE[phase];

  return (
    <CenteredShell>
      <Icon className="mb-4 size-8 text-ink-subtle" strokeWidth={1.5} />
      <p className="t-page-title mb-1.5">{copy.title}</p>
      <p className="t-label mb-6 max-w-[320px]">{copy.blurb}</p>

      <div className="mb-5 flex items-center gap-2">
        <StatusDot tone={meta.tone} />
        <span className="t-meta">{meta.label}</span>
      </div>

      {error ? <div className="mb-4 w-full max-w-[320px]"><InlineError message={error} /></div> : null}

      {!live && phase !== "ended" ? (
        <Button
          variant="primary"
          size="md"
          onClick={start}
          loading={phase === "requesting-mic" || phase === "connecting"}
        >
          <Phone className="size-3.5" strokeWidth={2} />
          Join call
        </Button>
      ) : phase === "ended" ? (
        <p className="t-label">You can close this page.</p>
      ) : (
        <div className="flex flex-col items-center gap-4">
          <div className="flex items-center gap-2" aria-hidden>
            {Array.from({ length: 24 }).map((_, i) => {
              const active = !muted && level * 24 * 1.6 > i;
              return (
                <span
                  key={i}
                  className={active ? "w-[2px] bg-ink" : "w-[2px] bg-line-strong"}
                  style={{ height: active ? `${Math.min(16, 4 + i * 0.6)}px` : "3px" }}
                />
              );
            })}
          </div>
          {muted ? <p className="t-meta text-critical">The assistant cannot hear you</p> : null}
          <div className="flex items-center gap-2">
            <Button onClick={toggleMute} title={muted ? "Unmute" : "Mute your microphone"}>
              {muted ? (
                <MicOff className="size-3.5 text-critical" strokeWidth={2} />
              ) : (
                <Mic className="size-3.5" strokeWidth={2} />
              )}
              {muted ? "Muted" : "Mute"}
            </Button>
            <Button onClick={stop}>
              <PhoneOff className="size-3.5" strokeWidth={2} />
              End call
            </Button>
          </div>
        </div>
      )}
    </CenteredShell>
  );
}

function CenteredShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-dvh flex-col items-center justify-center bg-canvas px-6 text-center">
      {children}
    </div>
  );
}
