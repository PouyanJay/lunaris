import { useAuth } from "./useAuth";
import { isLiveEnabled } from "../lib/product";

/** Whether Lunaris is currently two products rather than one.
 *
 *  The fork needs BOTH halves: the Live flag, and configured auth (the remembered product lives in
 *  the account, and there is no account to read without it). One shared predicate so the router and
 *  the switcher cannot drift into disagreeing — a switcher offering a destination the router will
 *  not route to would strand the user on a not-found. */
export function useProductFork(): boolean {
  const { enabled } = useAuth();
  return isLiveEnabled() && enabled;
}
