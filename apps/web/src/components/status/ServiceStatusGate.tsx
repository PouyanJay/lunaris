import type { ReactNode } from "react";

import { useServiceStatus } from "../../hooks/useServiceStatus";
import { prodControlBaseUrl } from "../../lib/prodOps";
import { ServiceOffline } from "./ServiceOffline";

/** Shows the app while the API is serving, and the offline page when it is not (production is
 *  switched off, or the API is down). Sits outside the auth gate so a visitor never meets a sign-in
 *  form that cannot work; an administrator signs in from the offline page instead. */
export function ServiceStatusGate({
  apiBaseUrl,
  children,
}: {
  apiBaseUrl: string;
  children: ReactNode;
}) {
  const { offline, checking, recheck } = useServiceStatus(apiBaseUrl);
  if (offline) {
    return (
      <ServiceOffline
        controlBaseUrl={prodControlBaseUrl(apiBaseUrl)}
        checking={checking}
        onRetry={recheck}
      />
    );
  }
  return <>{children}</>;
}
