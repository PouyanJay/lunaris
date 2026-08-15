#: The placeholder simulator, as one self-contained document (P2b T6).
#:
#: **Nothing here teaches anything, and that is the specification** (A3). What it proves is the
#: socket: it loads in a sandboxed frame, it lets the learner do one thing, and it reports what they
#: did back to the host in the shape a real simulator will use. Phase 3's factory replaces this
#: document; it does not replace the frame around it or the message it sends.
#:
#: **Self-contained on purpose.** No stylesheet, no script file, no font, no image — a frame served
#: with `sandbox="allow-scripts"` has an opaque origin, so every relative URL inside it resolves
#: against `null` and nothing external would load anyway. Inlining is not a shortcut here, it is the
#: only thing that works.
#:
#: The colours are literals rather than tokens, and this is the one place in the product where that
#: is right: the document is cross-origin from the SPA, so it cannot read a CSS custom property the
#: host defines. It follows `prefers-color-scheme` instead, which is what the host's own theme
#: follows when a learner has not overridden it.
STUB_SIM_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Placeholder simulator</title>
<style>
  :root { color-scheme: light dark; --ink: #12151c; --paper: #f7f8fa; --line: #cbd0d9;
          --quiet: #4b5563; }
  @media (prefers-color-scheme: dark) {
    :root { --ink: #e9ebee; --paper: #0f1115; --line: #2a2f38; --quiet: #8a909b; }
  }
  * { box-sizing: border-box; }
  body { margin: 0; padding: 16px; background: var(--paper); color: var(--ink);
         font: 13px/1.5 ui-sans-serif, system-ui, sans-serif; }
  h1 { margin: 0 0 4px; font-size: 13px; font-weight: 600; }
  p  { margin: 0 0 12px; color: var(--quiet); }
  label { display: block; margin-bottom: 8px; font-weight: 500; }
  input { width: 100%; }
  output { display: block; margin: 12px 0; font: 500 12px/1.4 ui-monospace, monospace;
           font-variant-numeric: tabular-nums; }
  button { font: inherit; padding: 6px 12px; border: 1px solid var(--line);
           border-radius: 5px; background: transparent; color: inherit; cursor: pointer; }
  button:hover:not(:disabled) { border-color: var(--quiet); }
  button:focus-visible { outline: none; box-shadow: 0 0 0 2px currentColor; }
  button:disabled { opacity: .5; cursor: default; }
  @media (prefers-reduced-motion: reduce) { * { transition: none !important; } }
</style>
</head>
<body>
  <h1>Placeholder simulator</h1>
  <p>Nothing is being simulated. This frame exists to prove the socket a real simulator will
     plug into.</p>

  <label for="dial">Move the dial, then send what you did</label>
  <input id="dial" type="range" min="0" max="100" value="50" step="1"
         aria-describedby="readout">
  <output id="readout" for="dial">dial = 50</output>

  <button id="send" type="button">Send what I did</button>

<script>
  var dial = document.getElementById("dial");
  var readout = document.getElementById("readout");
  var send = document.getElementById("send");
  var touched = false;

  dial.addEventListener("input", function () {
    touched = true;
    readout.textContent = "dial = " + dial.value;
  });

  send.addEventListener("click", function () {
    send.disabled = true;
    // The report is the simulator's own account of what the learner did, in words, because it goes
    // in through the ordinary answer path and is graded by the same separate grader against the
    // same staged criterion. A real simulator writes a real account here; this one is honest about
    // being a placeholder rather than inventing evidence of understanding it cannot observe.
    parent.postMessage({
      type: "lunaris.sim.report",
      appId: "lunaris.sim.stub",
      report: touched
        ? "In the placeholder simulator I moved the dial to " + dial.value +
          ". Nothing was actually simulated, so this shows only that the frame works."
        : "I opened the placeholder simulator but did not move anything."
    }, "*");
  });
</script>
</body>
</html>
"""
