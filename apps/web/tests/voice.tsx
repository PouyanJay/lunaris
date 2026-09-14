import { useState } from "react";
import { createRoot } from "react-dom/client";
import { AnswerForm } from "../src/components/live/AnswerForm";
import { Button } from "../src/components/primitives/Button";
import { authedFetch } from "../src/lib/apiClient";
import type { LiveSession } from "../src/lib/liveSession";
import "../src/index.css";

const api = new URLSearchParams(location.search).get("api")!;
async function request(path: string, init?: RequestInit): Promise<Response> {
  const response = await authedFetch(`${api}${path}`, init);
  if (!response.ok) throw new Error("Request failed. Continue with text or retry.");
  return response;
}
const initial = (await (await request("/test/session", { method: "POST" })).json()) as LiveSession;

function VoiceRoundtrip() {
  const [session, setSession] = useState(initial);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("Ready");
  const [error, setError] = useState<string | null>(null);
  const [audioRunning, setAudioRunning] = useState(false);
  const turn = session.turns.at(-1)!;
  const source = { turnSeq: turn.seq, runId: turn.runId };
  const prefix = `/api/live/sessions/${session.sessionId}`;

  async function perform(action: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch {
      setError("Voice request failed. Continue with text or retry.");
    } finally {
      setBusy(false);
    }
  }

  async function transcribe() {
    const recording = await (await request("/test/recording")).blob();
    const response = await request(
      `${prefix}/voice/transcriptions?turnSeq=${source.turnSeq}&runId=${source.runId}`,
      {
        method: "POST",
        headers: { "Content-Type": "audio/wav", "Idempotency-Key": crypto.randomUUID() },
        body: recording,
      },
    );
    const transcript = (await response.json()) as { text: string };
    setDraft(transcript.text);
    setStatus("Review your transcript before sending");
  }

  async function answer(text: string) {
    const response = await request(`${prefix}/turns`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ answer: text, answeringSeq: turn.seq }),
    });
    setSession((await response.json()) as LiveSession);
    setDraft("");
    setStatus("Answer saved");
  }

  async function speak() {
    const audio = new AudioContext({ sampleRate: 24000 });
    try {
      await audio.resume();
      setAudioRunning(audio.state === "running");
      const response = await request(`${prefix}/voice/speech`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source, operationId: crypto.randomUUID() }),
      });
      const reader = response.body!.getReader();
      let samples = 0;
      let pendingByte: number | undefined;
      let nextStart = audio.currentTime;
      const completions: Promise<void>[] = [];
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const bytes = new Uint8Array(value.byteLength + (pendingByte === undefined ? 0 : 1));
        if (pendingByte !== undefined) bytes[0] = pendingByte;
        bytes.set(value, pendingByte === undefined ? 0 : 1);
        const length = bytes.byteLength - (bytes.byteLength % 2);
        pendingByte = length === bytes.byteLength ? undefined : bytes[length];
        if (length === 0) continue;
        const data = new DataView(bytes.buffer, 0, length);
        const buffer = audio.createBuffer(1, length / 2, 24000);
        const channel = buffer.getChannelData(0);
        for (let i = 0; i < channel.length; i++) channel[i] = data.getInt16(i * 2, true) / 32768;
        const node = audio.createBufferSource();
        node.buffer = buffer;
        node.connect(audio.destination);
        completions.push(new Promise<void>((resolve) => (node.onended = () => resolve())));
        nextStart = Math.max(nextStart, audio.currentTime);
        node.start(nextStart);
        nextStart += buffer.duration;
        samples += channel.length;
      }
      if (pendingByte !== undefined) throw new Error("Incomplete PCM sample");
      await Promise.all(completions);
      setStatus(`Played ${samples} samples`);
    } finally {
      await audio.close();
    }
  }

  return (
    <main data-session-id={session.sessionId} data-audio-running={audioRunning}>
      <h1>Voice roundtrip</h1>
      {session.turns.map((item) => (
        <section key={item.runId} aria-label={`Turn ${item.seq}`}>
          <p>{item.tutor}</p>
          {item.answer && <p>{item.answer}</p>}
        </section>
      ))}
      <Button disabled={busy} onClick={() => void perform(transcribe)}>
        Transcribe fixture recording
      </Button>
      <AnswerForm
        key={`${turn.runId}:${draft}`}
        initialAnswer={draft}
        criterion={turn.criterion?.statement ?? null}
        busy={busy}
        onAnswer={(text) => void perform(() => answer(text))}
      />
      <Button disabled={busy} onClick={() => void perform(speak)}>
        Read tutor response
      </Button>
      <p role="status">{status}</p>
      {error && <p role="alert">{error}</p>}
    </main>
  );
}

createRoot(document.getElementById("root")!).render(<VoiceRoundtrip />);
