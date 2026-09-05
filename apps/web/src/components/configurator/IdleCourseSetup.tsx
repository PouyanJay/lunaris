import { useCallback, useEffect, useRef, useState } from "react";

import { useAutoHideScroll } from "../../hooks/useAutoHideScroll";
import type { BuildRequest } from "../../hooks/useCourseStream";
import { answersToClarification, recommendedAnswers } from "../../lib/clarification";
import { applyComposerLevel, type ComposerLevel } from "../../lib/composerLevel";
import { fetchBrief } from "../../lib/fetchBrief";
import { CourseLoadError } from "../../lib/loadCourse";
import type { BriefLoadState } from "../../types/clarifier";
import type { Product } from "../../lib/product";
import type { CourseRun, DiscoveryDepth } from "../../types/course";
import { TopicForm } from "../TopicForm";
import { LiveToggle } from "../gateway/LiveToggle";
import { PersonalizeMenu } from "./PersonalizeMenu";
import { ComposerFeatures } from "./ComposerFeatures";
import { ComposerOptions } from "./ComposerOptions";
import styles from "./IdleCourseSetup.module.css";

interface IdleCourseSetupProps {
  apiBaseUrl: string;
  /** Build the course from a request: the topic, the learner's confirmed clarification (absent →
   *  inference-only), the chosen search depth, and the "Official sources only" trust switch. */
  onGenerate: (request: BuildRequest) => void;
  /** Start a Lunaris Live session for the topic instead of compiling a course. Absent when Lunaris
   *  is a single product — the composer then only ever generates. */
  onStartLive?: ((topic: string) => void) | undefined;
  /** Open the operator/admin Settings panel (the rail only points there). */
  onOpenSettings: () => void;
  /** The run history (from the shell's useRuns). Read only to tell a first-time visitor from a
   *  returning one; the composer no longer lists builds. */
  runs?: CourseRun[];
  /** Whether that history has actually loaded. The parent collapses an unloaded history to an empty
   *  array, so without this the first-run explainer would flash up and vanish for every returning
   *  user. */
  runsLoaded?: boolean;
  /** Which product the composer opens in. Studio unless the caller says otherwise — Live's own rail
   *  opens it in Live mode (`/new?mode=live`) so its primary action does not send a learner out of
   *  the product they are standing in (journey live-session-lifecycle, T7). The URL is read by the
   *  shell rather than here, so this component still needs no router. */
  initialMode?: Product;
}

/**
 * The idle "new course" surface: a single centred column holding the composer.
 *
 * Every build setting lives inside the composer's box now, docked in a bar at its foot, so there is
 * no rail beside it and nothing to resize, collapse or turn into a drawer. This owns the topic, the
 * chosen mode, the build settings and the learner-tier brief lifecycle, so the confirmed values
 * thread straight into the build.
 *
 * A topic edit invalidates any brief read for the previous topic, so a stale clarifier can never
 * build.
 */
export function IdleCourseSetup({
  apiBaseUrl,
  onGenerate,
  onStartLive,
  onOpenSettings,
  runs = [],
  runsLoaded = false,
  initialMode = "studio",
}: IdleCourseSetupProps) {
  const [topic, setTopic] = useState("");
  // Which product the topic goes to. Studio is the default, so the existing path is untouched.
  const [mode, setMode] = useState<Product>(initialMode);
  const [depth, setDepth] = useState<DiscoveryDepth>("standard");
  // The composer's quick options bar: target level (mapped onto the brief's clarification) and the
  // per-build "Official sources only" trust switch. Level "recommended" = today's inferred default.
  const [level, setLevel] = useState<ComposerLevel>("recommended");
  const [officialOnly, setOfficialOnly] = useState(false);
  const [brief, setBrief] = useState<BriefLoadState>({ status: "blank" });
  const briefController = useRef<AbortController | null>(null);

  const mainRef = useRef<HTMLDivElement>(null);

  // Cancel any in-flight brief read on unmount so it can't settle on a gone component.
  useEffect(() => () => briefController.current?.abort(), []);

  // Reading the topic resets any brief that was read for the previous topic — its inference and
  // answers no longer apply, so it must not silently build the new topic with stale answers.
  const handleTopicChange = useCallback((value: string) => {
    setTopic(value);
    briefController.current?.abort();
    setBrief({ status: "blank" });
  }, []);

  const loadBrief = useCallback(() => {
    const trimmed = topic.trim();
    if (!trimmed) return;
    briefController.current?.abort();
    const controller = new AbortController();
    briefController.current = controller;
    setBrief({ status: "loading" });
    fetchBrief(apiBaseUrl, trimmed, controller.signal)
      .then((data) => {
        if (controller.signal.aborted) return;
        setBrief({ status: "ready", data, answers: recommendedAnswers(data.clarifier) });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        const message =
          error instanceof CourseLoadError
            ? error.message
            : "We couldn't read your goal. Try again.";
        setBrief({ status: "error", message });
      });
  }, [apiBaseUrl, topic]);

  const handleAnswerChange = useCallback((id: string, value: string) => {
    setBrief((prev) =>
      prev.status === "ready" ? { ...prev, answers: { ...prev.answers, [id]: value } } : prev,
    );
  }, []);

  // Build the clarification from the loaded brief (else inference-only), then let the options-bar
  // Level override its target level — mapping the quick control onto the brief, not duplicating it.
  // Depth and the official-only switch always accompany.
  const handleSubmit = useCallback(
    (submitted: string) => {
      const fromBrief =
        brief.status === "ready" ? answersToClarification(brief.answers) : undefined;
      // Live's promise is a session, not a build — so it must never reach the build control room.
      // The Studio-only build settings below are simply not consulted.
      if (mode === "live" && onStartLive) {
        onStartLive(submitted);
        return;
      }
      const clarification = applyComposerLevel(fromBrief, level);
      onGenerate({ topic: submitted, clarification, discoveryDepth: depth, officialOnly });
    },
    [brief, level, depth, officialOnly, mode, onStartLive, onGenerate],
  );

  useAutoHideScroll(mainRef);

  return (
    <div className={`${styles.column} scroller`} ref={mainRef}>
      <TopicForm
        value={topic}
        onChange={handleTopicChange}
        onSubmit={handleSubmit}
        heading={
          mode === "live"
            ? { lead: "What should we ", accent: "work through", tail: "?" }
            : { lead: "What do you want to ", accent: "learn", tail: "?" }
        }
        live={mode === "live"}
        modeControl={
          onStartLive ? (
            <LiveToggle on={mode === "live"} onChange={(on) => setMode(on ? "live" : "studio")} />
          ) : undefined
        }
        submitLabel={mode === "live" ? "Start session" : "Generate course"}
        options={
          <ComposerOptions
            mode={mode}
            depth={depth}
            onDepthChange={setDepth}
            level={level}
            onLevelChange={setLevel}
            officialOnly={officialOnly}
            onOfficialOnlyChange={setOfficialOnly}
            onOpenTrustedSources={onOpenSettings}
            personalize={
              <PersonalizeMenu
                topic={topic}
                brief={brief}
                onLoadBrief={loadBrief}
                onAnswerChange={handleAnswerChange}
              />
            }
          />
        }
      />
      {/* What a build does is first-run material: someone with completed courses does not need to
          be told, and the space is better spent on what they came back for. */}
      {runsLoaded && runs.length === 0 && <ComposerFeatures mode={mode} />}
    </div>
  );
}
