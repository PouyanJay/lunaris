import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

const MEDIA_LOAD_TIMEOUT_MS = 15_000;
interface PlaybackOptions {
  clip: { assetId: string; startS: number; endS: number };
  getSource: (assetId: string, signal: AbortSignal) => Promise<string>;
  onPlaybackStart?: (() => boolean | void) | undefined;
  interruptionKey?: string | number | undefined;
  registerStop?: ((stop: () => void) => () => void) | undefined;
}

/** Owns temporary media access, bounded playback and interruption for one mounted scope. */
export function useCorpusClipPlayback({
  clip,
  getSource,
  onPlaybackStart,
  interruptionKey,
  registerStop,
}: PlaybackOptions) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const request = useRef<AbortController | null>(null);
  const generation = useRef({ value: 0 });
  const [url, setUrl] = useState<string>();
  const [state, setState] = useState<"idle" | "loading" | "ready" | "error" | "unavailable">(
    "idle",
  );
  const [playing, setPlaying] = useState(false);
  const [waiting, setWaiting] = useState(false);
  const [time, setTime] = useState(clip.startS);

  useEffect(() => {
    const video = videoRef.current;
    const counter = generation.current;
    return () => {
      counter.value++;
      request.current?.abort();
      video?.pause();
      video?.removeAttribute("src");
      video?.load();
    };
  }, []);
  const stop = useCallback(() => {
    generation.current.value++;
    request.current?.abort();
    videoRef.current?.pause();
    setPlaying(false);
    setWaiting(false);
    setState((previous) => (previous === "loading" ? "idle" : previous));
  }, []);
  useLayoutEffect(() => registerStop?.(stop), [registerStop, stop]);
  useEffect(stop, [interruptionKey, stop]);

  useEffect(() => {
    if (state !== "loading" && !waiting) return;
    const timeout = window.setTimeout(() => {
      generation.current.value++;
      request.current?.abort();
      setUrl(undefined);
      videoRef.current?.pause();
      setWaiting(false);
      setPlaying(false);
      setState("error");
    }, MEDIA_LOAD_TIMEOUT_MS);
    return () => window.clearTimeout(timeout);
  }, [state, waiting]);

  function enforceBounds() {
    const video = videoRef.current;
    if (!video || video.seeking) return;
    if (video.currentTime < clip.startS) video.currentTime = clip.startS;
    if (video.currentTime >= clip.endS) {
      video.pause();
      if (video.currentTime !== clip.endS) video.currentTime = clip.endS;
      setPlaying(false);
      setWaiting(false);
    }
    setTime(Math.min(clip.endS, Math.max(clip.startS, video.currentTime)));
  }
  useEffect(() => {
    if (!playing) return;
    let frame: number;
    const tick = () => {
      const video = videoRef.current;
      if (video && video.currentTime >= clip.endS) {
        video.pause();
        video.currentTime = clip.endS;
        setTime(clip.endS);
        setPlaying(false);
        setWaiting(false);
        return;
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [playing, clip.endS]);

  async function load() {
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    const version = ++generation.current.value;
    setState("loading");
    setUrl(undefined);
    setPlaying(false);
    setWaiting(false);
    videoRef.current?.pause();
    try {
      const source = await getSource(clip.assetId, controller.signal);
      if (controller.signal.aborted || version !== generation.current.value) return;
      const parsed = new URL(source, location.href);
      if (
        parsed.protocol !== "https:" &&
        !(parsed.protocol === "http:" && parsed.origin === location.origin)
      ) {
        throw new Error("Invalid media URL");
      }
      setUrl(parsed.href);
    } catch {
      if (!controller.signal.aborted && version === generation.current.value) setState("error");
    }
  }
  async function play() {
    const video = videoRef.current;
    if (!video || state !== "ready") return;
    if (playing || waiting) {
      generation.current.value++;
      video.pause();
      setPlaying(false);
      setWaiting(false);
      return;
    }
    const version = generation.current.value;
    if (video.currentTime >= clip.endS || video.currentTime < clip.startS)
      video.currentTime = clip.startS;
    try {
      if (onPlaybackStart?.() === false) return;
      setWaiting(true);
      await video.play();
      if (version !== generation.current.value) video.pause();
      else setWaiting(false);
    } catch {
      if (version === generation.current.value) {
        setWaiting(false);
        setState("error");
      }
    }
  }
  function metadataLoaded() {
    const video = videoRef.current;
    if (!video) return;
    if (!Number.isFinite(video.duration) || video.duration < clip.endS) {
      video.pause();
      setState("unavailable");
      return;
    }
    video.currentTime = clip.startS;
    setTime(clip.startS);
    setState("ready");
  }
  function seek(seconds: number) {
    if (!videoRef.current) return;
    videoRef.current.currentTime = Math.min(clip.endS, Math.max(clip.startS, seconds));
    enforceBounds();
  }
  return {
    videoRef,
    url,
    state,
    playing,
    waiting,
    time,
    load,
    play,
    seek,
    mediaEvents: {
      onLoadedMetadata: metadataLoaded,
      onPlay: () => setPlaying(true),
      onPlaying: () => {
        setWaiting(false);
        setPlaying(true);
      },
      onWaiting: () => {
        if (playing || waiting) setWaiting(true);
      },
      onPause: () => {
        setPlaying(false);
        setWaiting(false);
      },
      onLoadedData: enforceBounds,
      onSeeked: enforceBounds,
      onTimeUpdate: enforceBounds,
      onError: () => {
        if (url) {
          setState("error");
          setPlaying(false);
          setWaiting(false);
        }
      },
    },
  };
}
