import { useCallback, useContext, useSyncExternalStore } from "react";
import { isNodeAsset, type NodeAsset } from "../../lib/liveMaterials";
import { sessionMaterialMedia } from "../../lib/sessionMaterialMedia";
import { CorpusClipPlayer } from "./CorpusClipPlayer";
import { SessionMediaContext } from "./SessionMediaContext";
import styles from "./SessionMaterials.module.css";

interface SessionMaterialsProps {
  apiBaseUrl: string;
  sessionId: string;
  turnSeq: number;
  runId: string;
  move: string;
  materials?: NodeAsset[] | undefined;
}

/** Verified supporting material complements the standing assessment and never collects credit. */
export function SessionMaterials(props: SessionMaterialsProps) {
  if (props.move === "retrieve") return null;
  const materials = (props.materials ?? []).filter(
    (asset) => isNodeAsset(asset) && asset.verification?.sourceDigest === asset.sourceDigest,
  );
  if (!materials.length) return null;
  const unique = [...new Map(materials.map((asset) => [asset.assetId, asset])).values()];
  return (
    <section className={styles.root} aria-label="Course material">
      {unique.map((asset) =>
        asset.kind === "video_clip" && asset.clip ? (
          <MaterialClip key={asset.assetId} {...props} asset={asset} />
        ) : (
          <section
            className={styles.material}
            key={asset.assetId}
            aria-label={asset.kind === "assessment" ? "Ungraded practice" : "Source reading"}
          >
            <p className={styles.label}>
              {asset.kind === "assessment" ? "Ungraded practice" : "Source reading"}
            </p>
            <h3>{asset.title}</h3>
            <p className={styles.excerpt}>{asset.excerpt}</p>
            <p className={styles.source}>{asset.sourceLabel}</p>
          </section>
        ),
      )}
    </section>
  );
}

function MaterialClip({ asset, ...scope }: SessionMaterialsProps & { asset: NodeAsset }) {
  const media = useContext(SessionMediaContext);
  const blocked = useSyncExternalStore(
    media?.subscribe ?? subscribeIdle,
    media?.isBlocked ?? isIdle,
  );
  const owner = `clip:${asset.assetId}`;
  const registerStop = useCallback(
    (stop: () => void) => media?.register(owner, stop) ?? (() => {}),
    [media, owner],
  );
  const getSource = useCallback(
    (assetId: string, signal: AbortSignal) =>
      sessionMaterialMedia(
        { apiBaseUrl: scope.apiBaseUrl, sessionId: scope.sessionId, turnSeq: scope.turnSeq },
        assetId,
        signal,
      ),
    [scope.apiBaseUrl, scope.sessionId, scope.turnSeq],
  );
  if (!asset.clip) return null;
  return (
    <CorpusClipPlayer
      clip={{ ...asset.clip, assetId: asset.assetId, sourceLabel: asset.sourceLabel }}
      getSource={getSource}
      playbackScope={JSON.stringify([
        scope.apiBaseUrl,
        scope.sessionId,
        scope.turnSeq,
        scope.runId,
      ])}
      onPlaybackStart={() => media?.activate(owner)}
      registerStop={registerStop}
      disabled={blocked}
    />
  );
}

const subscribeIdle = () => () => {};
const isIdle = () => false;
