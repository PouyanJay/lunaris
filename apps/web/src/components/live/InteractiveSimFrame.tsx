import type { SimContract } from "../../lib/simContract";
import { Button } from "../primitives/Button";
import { useSimBridge } from "./useSimBridge";
import styles from "./SimFrame.module.css";

interface Props {
  url: string;
  title: string;
  appId: string;
  contract: SimContract;
  answerable: boolean;
  busy: boolean;
}

/** Displays the shared instrument; gestures teach and the ordinary answer form grades. */
export function InteractiveSimFrame({ url, title, appId, contract, answerable, busy }: Props) {
  const bridge = useSimBridge(contract, appId, answerable && !busy);
  if (contract.version !== 1)
    return (
      <p role="status">This simulator needs a newer app version. Continue with your explanation.</p>
    );
  const status = !bridge.ready
    ? bridge.unavailable
      ? "The simulator could not load. Continue with your explanation."
      : "Loading the simulator…"
    : bridge.working
      ? "Your tutor is looking at the change…"
      : bridge.message;
  return (
    <div className={styles.mount}>
      <iframe
        ref={bridge.frame}
        className={styles.frame}
        src={url}
        title={title}
        sandbox="allow-scripts"
        referrerPolicy="no-referrer"
        onLoad={bridge.initialize}
        onError={bridge.markUnavailable}
      />
      <p className={styles.status} role={bridge.failed ? "alert" : "status"}>
        {status}
      </p>
      {bridge.failed && answerable && !busy ? (
        <Button disabled={bridge.working} onClick={bridge.retry}>
          Retry tutor response
        </Button>
      ) : null}
    </div>
  );
}
