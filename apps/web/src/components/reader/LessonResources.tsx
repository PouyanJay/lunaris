import type { Resource, ResourceKind } from "../../types/course";
import { SourceTrust } from "../primitives/SourceTrust";
import { ResourceThumb } from "./ResourceThumb";
import { VideoFacade } from "./VideoFacade";
import { youTubeId } from "./youtube";
import styles from "./LessonResources.module.css";

interface LessonResourcesProps {
  resources: Resource[];
}

/** One curated resource card. A recognisable YouTube URL is always treated as a video — it plays
 *  in-reader (facade → nocookie embed + lightbox) and reads as "video" — whatever the curator
 *  labelled it, so a mislabeled `kind: "article"` on a youtube.com link is never a dead "READ" card.
 *  The URL is parsed once and drives both the media and the kind word; anything else keeps its
 *  decorative thumbnail and authored kind, with the title link as the action. */
function ResourceCard({ resource }: { resource: Resource }) {
  const videoId = youTubeId(resource.url);
  const kind: ResourceKind = videoId !== null ? "video" : resource.kind;

  return (
    <li className={styles.item}>
      {videoId !== null ? (
        <VideoFacade videoId={videoId} title={resource.title} />
      ) : (
        <ResourceThumb kind={resource.kind} url={resource.url} title={resource.title} />
      )}
      <div className={styles.body}>
        <div className={styles.head}>
          <a className={styles.link} href={resource.url} target="_blank" rel="noopener noreferrer">
            {resource.title}
          </a>
          {resource.duration && (
            <span className={`mono ${styles.duration}`}>{resource.duration}</span>
          )}
        </div>
        {resource.why && <p className={styles.why}>{resource.why}</p>}
        <div className={styles.meta}>
          <span className={`mono ${styles.kind}`}>{kind}</span>
          {resource.source && <span className={`mono ${styles.source}`}>{resource.source}</span>}
          <SourceTrust tier={resource.trustTier} credibility={resource.credibility} />
        </div>
      </div>
    </li>
  );
}

/** The curated external resources attached to a teaching phase (P7.4) — suggested aids the learner
 *  can follow beyond the lesson. Each card leads with a thumbnail (a real YouTube frame + play
 *  affordance for videos, a tokened kind glyph otherwise — req 3), then its title link (new tab),
 *  source domain (mono), trust tier, optional runtime, and the one-line "why this helps". The caller
 *  renders it only when `resources` is non-empty, so a phase with no vetted aid simply omits it. */
export function LessonResources({ resources }: LessonResourcesProps) {
  return (
    <section className={styles.panel} aria-label="Resources">
      <h4 className={styles.title}>Resources</h4>
      <ul className={styles.list}>
        {resources.map((resource) => (
          <ResourceCard key={resource.url} resource={resource} />
        ))}
      </ul>
    </section>
  );
}
