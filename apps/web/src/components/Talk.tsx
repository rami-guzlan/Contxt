// Talk to the Brain: hold Space (anywhere but a text field) or the Talk button, and what you say
// lands in Capture, turned into text on this computer. A quick tap starts listening until the
// next tap, for a longer thought. Recording a meeting (Capture's Record) uses the same recorder.

import { Mic, Square, X } from "lucide-react";
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router";

import { useTalkUpload } from "../api/hooks";
import type { Note } from "../api/types";

const HOLD_MS = 300; // a press longer than this is push-to-talk; a shorter one a tap
const SHORTEST_MS = 500; // less than this is not worth sending
const TYPES = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"];

type State = "idle" | "asking" | "listening" | "sending";

interface Talk {
  state: State;
  /** A tap started it: it listens until the next press. */
  latched: boolean;
  seconds: number;
  error: string | null;
  saved: Note | null;
  press(): void;
  release(): void;
  dismiss(): void;
}

const TalkContext = createContext<Talk | null>(null);

export const useTalk = () => useContext(TalkContext);

export function canRecord(): boolean {
  return typeof window !== "undefined" && typeof window.MediaRecorder !== "undefined" && !!navigator.mediaDevices?.getUserMedia;
}

/** The microphone, recorded until stopped, as one audio Blob. */
export function useRecorder() {
  const recorder = useRef<MediaRecorder | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const chunks = useRef<Blob[]>([]);
  const begin = useCallback(async () => {
    const media = await navigator.mediaDevices.getUserMedia({ audio: true });
    stream.current = media;
    const type = TYPES.find((t) => MediaRecorder.isTypeSupported?.(t)) ?? "";
    const rec = new MediaRecorder(media, type ? { mimeType: type } : undefined);
    chunks.current = [];
    rec.ondataavailable = (event) => {
      if (event.data.size) chunks.current.push(event.data);
    };
    rec.start(1000);
    recorder.current = rec;
  }, []);
  const end = useCallback(
    () =>
      new Promise<Blob | null>((resolve) => {
        const rec = recorder.current;
        if (!rec) {
          resolve(null);
          return;
        }
        rec.onstop = () => {
          stream.current?.getTracks().forEach((track) => track.stop());
          stream.current = null;
          recorder.current = null;
          resolve(new Blob(chunks.current, { type: rec.mimeType || "audio/webm" }));
        };
        rec.stop();
      }),
    [],
  );
  return { begin, end };
}

/** Is the key press meant for a field the person is typing in? */
function typing(target: EventTarget | null): boolean {
  const element = target as HTMLElement | null;
  if (!element || typeof element.tagName !== "string") return false;
  return (
    element.isContentEditable ||
    ["INPUT", "TEXTAREA", "SELECT", "BUTTON"].includes(element.tagName) ||
    !!element.closest?.("[contenteditable='true']")
  );
}

export function TalkProvider({ children }: { children: ReactNode }) {
  const upload = useTalkUpload();
  const { begin, end } = useRecorder();
  const [state, setState] = useState<State>("idle");
  const [latched, setLatched] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<Note | null>(null);
  const now = useRef<State>("idle");
  const tap = useRef(false);
  const pressedAt = useRef(0);
  const startedAt = useRef(0);

  const move = useCallback((next: State) => {
    now.current = next;
    setState(next);
  }, []);

  const finish = useCallback(async () => {
    move("sending");
    tap.current = false;
    setLatched(false);
    const blob = await end();
    if (!blob || Date.now() - startedAt.current < SHORTEST_MS) {
      move("idle");
      setError("That was too short to hear. Hold a little longer.");
      return;
    }
    upload.mutate(blob, {
      onSuccess: (note) => {
        setSaved(note);
        move("idle");
      },
      onError: (caught) => {
        move("idle");
        setError(caught instanceof Error ? caught.message : "It could not be sent. Try again.");
      },
    });
  }, [end, move, upload]);

  const start = useCallback(async () => {
    setError(null);
    setSaved(null);
    if (!canRecord()) {
      setError("This browser can't record here.");
      return;
    }
    move("asking");
    try {
      await begin();
    } catch {
      move("idle");
      setError("The microphone is blocked. Allow it for this site in your browser, then try again.");
      return;
    }
    startedAt.current = Date.now();
    move("listening");
  }, [begin, move]);

  const press = useCallback(() => {
    pressedAt.current = Date.now();
    if (now.current === "listening" && tap.current) {
      void finish();
    } else if (now.current === "idle") {
      tap.current = false;
      void start();
    }
  }, [finish, start]);

  const release = useCallback(() => {
    if (now.current === "asking") {
      // Released while the browser asked for the microphone: listen once it is allowed,
      // until the next press.
      tap.current = true;
      setLatched(true);
      return;
    }
    if (now.current !== "listening" || tap.current) return;
    if (Date.now() - pressedAt.current < HOLD_MS) {
      tap.current = true;
      setLatched(true);
      return;
    }
    void finish();
  }, [finish]);

  const dismiss = useCallback(() => {
    setError(null);
    setSaved(null);
  }, []);

  // Hold Space anywhere but a field to talk.
  useEffect(() => {
    const down = (event: KeyboardEvent) => {
      if (event.code !== "Space" || event.repeat || event.altKey || event.ctrlKey || event.metaKey || typing(event.target)) return;
      event.preventDefault();
      press();
    };
    const up = (event: KeyboardEvent) => {
      if (event.code !== "Space" || typing(event.target)) return;
      event.preventDefault();
      release();
    };
    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    return () => {
      window.removeEventListener("keydown", down);
      window.removeEventListener("keyup", up);
    };
  }, [press, release]);

  useEffect(() => {
    if (state !== "listening") return;
    setSeconds(0);
    const timer = window.setInterval(() => setSeconds(Math.floor((Date.now() - startedAt.current) / 1000)), 500);
    return () => window.clearInterval(timer);
  }, [state]);

  useEffect(() => {
    if (!saved) return;
    const timer = window.setTimeout(() => setSaved(null), 10_000);
    return () => window.clearTimeout(timer);
  }, [saved]);

  const value: Talk = { state, latched, seconds, error, saved, press, release, dismiss };
  return (
    <TalkContext.Provider value={value}>
      {children}
      <TalkStatus talk={value} />
    </TalkContext.Provider>
  );
}

/** What the microphone is doing, and where what was said went. */
function TalkStatus({ talk }: { talk: Talk }) {
  const { state, latched, seconds, error, saved } = talk;
  if (state === "idle" && !error && !saved) return null;
  return (
    <div className={`talk-status${state === "listening" ? " live" : ""}`} role="status" aria-live="polite">
      {state === "asking" ? <span>Allow the microphone to talk to your Brain</span> : null}
      {state === "listening" ? (
        <>
          <span className="talk-dot" aria-hidden="true" />
          <span>
            Listening {formatSeconds(seconds)}. {latched ? "Press again to send." : "Let go to send."}
          </span>
        </>
      ) : null}
      {state === "sending" ? <span>Sending…</span> : null}
      {state === "idle" && saved ? (
        <span>
          Saved to Capture, turning it into text. <Link to={`/capture/${encodeURIComponent(saved.id)}`}>Open it</Link>
        </span>
      ) : null}
      {state === "idle" && error ? <span className="error">{error}</span> : null}
      {state === "idle" ? (
        <button type="button" className="link" aria-label="Close" onClick={talk.dismiss}>
          <X className="button-icon" aria-hidden="true" />
        </button>
      ) : null}
    </div>
  );
}

function formatSeconds(total: number): string {
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

/** Hold to talk, or tap to start and tap again to stop. Space does the same. */
export function TalkButton({ big = false }: { big?: boolean }) {
  const talk = useTalk();
  if (!talk) return null;
  const live = talk.state === "listening";
  return (
    <button
      type="button"
      className={`talk-button${big ? " big" : ""}${live ? " live" : ""}`}
      aria-pressed={live}
      data-tour="talk"
      title="Hold to talk, or tap to start and tap again to send. Holding Space works too."
      onPointerDown={(event) => {
        if (event.button !== 0) return;
        event.preventDefault();
        talk.press();
      }}
      onPointerUp={() => talk.release()}
      onPointerLeave={() => {
        if (live && !talk.latched) talk.release();
      }}
      onKeyDown={(event) => {
        if (event.key !== "Enter" && event.key !== " ") return;
        event.preventDefault();
        if (!event.repeat) talk.press();
      }}
      onKeyUp={(event) => {
        if (event.key !== "Enter" && event.key !== " ") return;
        event.preventDefault();
        talk.release();
      }}
    >
      {live ? <Square className="button-icon" aria-hidden="true" /> : <Mic className="button-icon" aria-hidden="true" />}
      {live ? (talk.latched ? "Send" : "Listening") : big ? "Hold to talk" : "Talk"}
    </button>
  );
}
