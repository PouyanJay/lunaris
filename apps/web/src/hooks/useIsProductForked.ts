import { useAuth } from "./useAuth";
import { isLiveEnabled } from "../lib/product";

/** Whether Lunaris is currently two products rather than one.
 *
 *  The fork needs BOTH halves: the Live flag, and configured auth — Live is a signed-in product, so
 *  offering it to an unauthenticated app would route somewhere that cannot work. One shared
 *  predicate so the router and the composer cannot drift into disagreeing; a composer offering a
 *  destination the router will not route to would strand the learner on a not-found. */
export function useIsProductForked(): boolean {
  const { enabled } = useAuth();
  return isLiveEnabled() && enabled;
}
