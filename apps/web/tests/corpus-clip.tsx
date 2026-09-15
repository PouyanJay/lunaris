import { useState } from "react";
import { createRoot } from "react-dom/client";
import { CorpusClipPlayer } from "../src/components/live/CorpusClipPlayer";
import { Button } from "../src/components/primitives/Button";
import "../src/index.css";

const clip = {
  assetId: "fixture-clip",
  title: "Bounded fixture video",
  startS: 0.5,
  endS: 1.4,
  transcript: [{ startS: 0.5, endS: 1.4, text: "This is a bounded excerpt." }],
  sourceLabel: "Fixture course · Verified excerpt",
};
/** Browser-only media fixture with turn and voice interruption controls. */
export function ClipFixture() {
  const [turn, setTurn] = useState(1);
  const [interruption, setInterruption] = useState(0);
  const [mounted, setMounted] = useState(true);
  const [starts, setStarts] = useState(0);
  return (
    <main>
      <h1>Clip integration</h1>
      {mounted && (
        <CorpusClipPlayer
          clip={clip}
          playbackScope={String(turn)}
          interruptionKey={interruption}
          onPlaybackStart={() => setStarts((count) => count + 1)}
          getSource={async () => new URL("/test-fixture.mp4", location.href).href}
        />
      )}
      <Button onClick={() => setTurn((value) => value + 1)}>Next turn</Button>
      <Button onClick={() => setInterruption((value) => value + 1)}>Interrupt with voice</Button>
      <Button onClick={() => setMounted(false)}>Close surface</Button>
      <output aria-label="Playback starts">{starts}</output>
    </main>
  );
}
createRoot(document.getElementById("root")!).render(<ClipFixture />);
