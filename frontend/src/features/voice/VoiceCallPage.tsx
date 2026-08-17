import { useCallback, useEffect, useRef, useState } from "react";
import {
  Room,
  RoomEvent,
  Track,
  createAudioAnalyser,
  type RemoteTrack,
  type RemoteParticipant,
} from "livekit-client";
import { Page } from "@/components/AppShell";
import { Panel, PanelHeader, StatusDot, EmptyState, type Tone } from "@/components/ui/primitives";
import { Button, InlineError } from "@/components/ui/controls";
import { useActivityFeed, useActivityFeedRealtime } from "@/lib/queries";
import { api, ApiError } from "@/lib/api";
import { formatClock } from "@/lib/format";
import { Phone, PhoneOff, Mic, MicOff, Radio } from "lucide-react";

/**
 * Every connection state is visible. A call UI that shows nothing between
 * "click" and "talking" leaves the user unsure whether it is broken, which on
 * a stage is indistinguishable from it actually being broken.
 */
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
  connected: { label: "Connected — waiting for agent", tone: "warning" },
  "agent-joined": { label: "Agent on the line", tone: "success" },
  reconnecting: { label: "Reconnecting…", tone: "warning" },
  ended: { label: "Call ended", tone: "neutral" },
  failed: { label: "Call failed", tone: "critical" },
};

interface Turn {
  id: string;
  who: "customer" | "agent";
  text: string;
  final: boolean;
}

export function VoiceCallPage() {
  useActivityFeedRealtime();
  const activity = useActivityFeed(40);

  const [phase, setPhase] = useState<Phase>("idle");
  const [error, setError] = useState<string | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [level, setLevel] = useState(0);
  const [muted, setMuted] = useState(false);

  const roomRef = useRef<Room | null>(null);
  const cleanupAnalyser = useRef<(() => void) | null>(null);
  const transcriptEnd = useRef<HTMLDivElement>(null);

  useEffect(() => {
    transcriptEnd.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns]);

  const teardown = useCallback(async () => {
    cleanupAnalyser.current?.();
    cleanupAnalyser.current = null;
    await roomRef.current?.disconnect();
    roomRef.current = null;
    setLevel(0);
    setMuted(false);
  }, []);

  /** Stops publishing audio entirely — the agent hears silence, not quiet. */
  const toggleMute = useCallback(async () => {
    const room = roomRef.current;
    if (!room) return;
    const next = !muted;
    await room.localParticipant.setMicrophoneEnabled(!next);
    setMuted(next);
  }, [muted]);

  useEffect(() => () => void teardown(), [teardown]);

  const start = async () => {
    setError(null);
    setTurns([]);
    setPhase("requesting-mic");

    let session;
    try {
      session = await api.voiceSession();
    } catch (e) {
      setPhase("failed");
      setError(
        e instanceof ApiError
          ? e.message
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
        // The agent is the only other participant that ever joins.
        if (p.identity.startsWith("agent") || p.isAgent) setPhase("agent-joined");
      })
      .on(RoomEvent.TrackSubscribed, (track: RemoteTrack) => {
        if (track.kind === Track.Kind.Audio) {
          track.attach();          // plays through the default output
          setPhase("agent-joined");
        }
      })
      .on(RoomEvent.TranscriptionReceived, (segments, participant) => {
        const fromAgent = participant?.isAgent ?? participant?.identity?.startsWith("agent") ?? false;
        setTurns((prev) => {
          const next = [...prev];
          for (const seg of segments) {
            const i = next.findIndex((t) => t.id === seg.id);
            const turn: Turn = {
              id: seg.id,
              who: fromAgent ? "agent" : "customer",
              text: seg.text,
              final: seg.final,
            };
            // Interim segments are replaced in place, so the transcript
            // corrects itself rather than repeating half-heard words.
            if (i >= 0) next[i] = turn;
            else next.push(turn);
          }
          return next;
        });
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
          ? "Microphone permission was refused. Allow it in the browser and try again."
          : "Could not connect. Check that the LiveKit server is running (make livekit).",
      );
      await teardown();
    }
  };

  const stop = async () => {
    await teardown();
    setPhase("ended");
  };

  const live = phase === "connected" || phase === "agent-joined" || phase === "reconnecting";
  const meta = PHASE[phase];

  return (
    <Page title="Live call">
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        {/* ------------------------------------------------------- call */}
        <Panel className="flex flex-col">
          <PanelHeader
            title="Customer call"
            action={
              <span className="flex items-center gap-2">
                <StatusDot tone={meta.tone} />
                <span className="t-meta">{meta.label}</span>
              </span>
            }
          />

          <div className="flex items-center gap-3 border-b border-line px-4 py-3">
            {!live ? (
              <Button variant="primary" size="md" onClick={start}
                loading={phase === "requesting-mic" || phase === "connecting"}>
                <Phone className="size-3.5" strokeWidth={2} />
                Start call
              </Button>
            ) : (
              <Button size="md" onClick={stop}>
                <PhoneOff className="size-3.5" strokeWidth={2} />
                End call
              </Button>
            )}

            {live ? (
              <>
                <Button onClick={toggleMute} title={muted ? "Unmute" : "Mute your microphone"}>
                  {muted ? (
                    <MicOff className="size-3.5 text-critical" strokeWidth={2} />
                  ) : (
                    <Mic className="size-3.5" strokeWidth={2} />
                  )}
                  {muted ? "Muted" : "Mute"}
                </Button>

                {/* Real microphone level, not an animation — a flat bar means
                    the mic genuinely is not picking anything up. */}
                <span className="flex h-4 items-center gap-[2px]" aria-hidden>
                  {Array.from({ length: 24 }).map((_, i) => {
                    const active = !muted && level * 24 * 1.6 > i;
                    return (
                      <span key={i}
                        className={active ? "w-[2px] bg-ink" : "w-[2px] bg-line-strong"}
                        style={{ height: active ? `${Math.min(16, 4 + i * 0.6)}px` : "3px" }} />
                    );
                  })}
                </span>

                {muted ? (
                  <span className="t-meta text-critical">
                    The agent cannot hear you
                  </span>
                ) : null}
              </>
            ) : null}
          </div>

          {error ? <div className="px-4 py-3"><InlineError message={error} /></div> : null}

          <div className="min-h-[320px] flex-1 overflow-y-auto px-4 py-3">
            {turns.length === 0 ? (
              <EmptyState
                icon={Phone}
                title={live ? "Listening…" : "No call in progress"}
                description={
                  live
                    ? "Say hello — the transcript appears here."
                    : "Start a call and speak. The AI answers, books, and the decisions appear on the right."
                }
              />
            ) : (
              <ul className="space-y-2.5">
                {turns.map((t) => (
                  <li key={t.id} className="flex gap-3">
                    <span className={[
                      "w-[68px] shrink-0 pt-px text-[11px] font-medium uppercase tracking-wide",
                      t.who === "agent" ? "text-ink" : "text-ink-subtle",
                    ].join(" ")}>
                      {t.who === "agent" ? "AI" : "Customer"}
                    </span>
                    <span className={[
                      "t-cell",
                      t.who === "agent" ? "text-ink" : "text-ink-muted",
                      t.final ? "" : "opacity-60",
                    ].join(" ")}>
                      {t.text}
                    </span>
                  </li>
                ))}
                <div ref={transcriptEnd} />
              </ul>
            )}
          </div>
        </Panel>

        {/* --------------------------------------------------- activity */}
        <Panel className="flex flex-col">
          <PanelHeader
            title="AI activity"
            description="What the system decided, as it decided it"
            action={
              <span className="flex items-center gap-1.5">
                <Radio className="size-3.5 text-success" strokeWidth={2} />
                <span className="t-meta">live</span>
              </span>
            }
          />
          <div className="min-h-[380px] flex-1 overflow-y-auto">
            {!activity.data?.length ? (
              <EmptyState icon={Radio} title="Nothing yet"
                description="Decisions stream in here the moment they happen." />
            ) : (
              <ul className="divide-y divide-line">
                {activity.data.map((e) => (
                  <li key={e.id} className="flex items-baseline gap-3 px-4 py-2.5">
                    <span className="t-meta shrink-0">{formatClock(e.created_at)}</span>
                    <StatusDot
                      tone={e.status === "failure" ? "critical"
                          : e.status === "blocked" ? "warning" : "success"}
                      className="translate-y-[3px]"
                    />
                    <span className="min-w-0 flex-1 t-cell">{e.summary}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </Panel>
      </div>
    </Page>
  );
}
