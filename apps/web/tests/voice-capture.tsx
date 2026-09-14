import { useState } from "react";
import { createRoot } from "react-dom/client";
import { useVoiceCapture } from "../src/components/live/voice/useVoiceCapture";
import { AnswerForm } from "../src/components/live/AnswerForm";
import type { LiveSession } from "../src/lib/liveSession";
import "../src/index.css";
const api = new URLSearchParams(location.search).get("api")!;
const session: LiveSession = await (await fetch(`${api}/test/session`, { method: "POST" })).json();
function Capture() {
  const [draft, setDraft] = useState("");
  const turn = session.turns.at(-1)!;
  const voice = useVoiceCapture({
    apiBaseUrl: api,
    sessionId: session.sessionId,
    source: { turnSeq: turn.seq, runId: turn.runId },
    onTranscript: (result) => setDraft(result.text),
  });
  return (
    <main data-session-id={session.sessionId}>
      <h1>Microphone verification</h1>
      <button onClick={() => void voice.start()}>Speak</button>
      <button onClick={() => void voice.finish()}>Finish recording</button>
      <button onClick={voice.cancel}>Cancel recording</button>
      <p role="status">{voice.status}</p>
      {voice.error && <p role="alert">{voice.error}</p>}
      <AnswerForm
        key={draft}
        initialAnswer={draft}
        criterion={null}
        busy={false}
        onAnswer={() => {}}
      />
    </main>
  );
}
createRoot(document.getElementById("root")!).render(<Capture />);
