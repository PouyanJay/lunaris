import type { Resource, ResourceKind } from "../../types/course";
import { SourceTrust } from "../primitives/SourceTrust";
import { ResourceThumb } from "./ResourceThumb";
import { VideoFacade } from "./VideoFacade";
import { youTubeId } from "./youtube";
import styles from "./LessonResources.module.css";

interface LessonResourcesProps {
  resources: Resource[];
}

/** The kind a resource should *render* as: a recognisable YouTube URL is always a video, whatever the
 *  curator labelled it (a mislabeled `kind: "article"` on a youtube.com link must still read + play as
 *  a video, not a "READ" card). Non-YouTube resources keep their authored kind. */
function effectiveKind(resource: Resource): ResourceKind {
  return youTubeId(resource.url) !== null ? "video" : resource.kind;
}

/** A YouTube video plays inside the reader (facade → nocookie embed + lightbox); any other resource
 *  keeps the decorative thumbnail, with its title link as the action. Keyed off the URL, not the
 *  authored kind, so a mislabeled youtube link still plays. */
function ResourceMedia({ resource }: { resource: Resource }) {
  const videoId = youTubeId(resource.url);
  if (videoId) return <VideoFacade videoId={videoId} title={resource.title} />;
  return <ResourceThumb kind={resource.kind} url={resource.url} title={resource.title} />;
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
          <li key={resource.url} className={styles.item}>
            <ResourceMedia resource={resource} />
            <div className={styles.body}>
              <div className={styles.head}>
                <a
                  className={styles.link}
                  href={resource.url}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  {resource.title}
                </a>
                {resource.duration && (
                  <span className={`mono ${styles.duration}`}>{resource.duration}</span>
                )}
              </div>
              {resource.why && <p className={styles.why}>{resource.why}</p>}
              <div className={styles.meta}>
                <span className={`mono ${styles.kind}`}>{effectiveKind(resource)}</span>
                {resource.source && (
                  <span className={`mono ${styles.source}`}>{resource.source}</span>
                )}
                <SourceTrust tier={resource.trustTier} credibility={resource.credibility} />
              </div>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
