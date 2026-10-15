import type { ReactNode } from "react";

import { useServiceStatus } from "../../hooks/useServiceStatus";
import { ServiceOffline } from "./ServiceOffline";

/** Shows the app while the API is serving, and the offline notice when it is not (production is
 *  switched off, or the API is down). Sits outside the auth gate so a visitor never meets a sign-in
 *  form that cannot work. */
export function ServiceStatusGate({
  apiBaseUrl,
  children,
}: {
  apiBaseUrl: string;
  children: ReactNode;
}) {
  const { offline } = useServiceStatus(apiBaseUrl);
  if (offline) return <ServiceOffline />;
  return <>{children}</>;
}
