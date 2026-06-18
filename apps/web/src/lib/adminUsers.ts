import { authedFetch } from "./apiClient";

/** One account on the admin user-management list (mirrors the API's AdminAccountView). */
export interface AdminAccount {
  id: string;
  email: string | null;
  createdAt: string | null;
  lastSignInAt: string | null;
  emailConfirmed: boolean;
  isAdmin: boolean;
  isSelf: boolean;
}

export class AdminUsersError extends Error {
  constructor(message: string, options?: ErrorOptions) {
    super(message, options);
    this.name = "AdminUsersError";
  }
}

async function detailOf(response: Response): Promise<string | undefined> {
  return response
    .json()
    .then((body: { detail?: string }) => body?.detail)
    .catch(() => undefined);
}

/** Admin: list every account. 403 unless the caller is an admin. */
export async function fetchAdminUsers(
  apiBaseUrl: string,
  signal?: AbortSignal,
): Promise<AdminAccount[]> {
  let response: Response;
  try {
    response = await authedFetch(`${apiBaseUrl}/api/admin/users`, signal ? { signal } : undefined);
  } catch (cause) {
    throw new AdminUsersError("Could not reach the user service.", { cause });
  }
  if (!response.ok) {
    throw new AdminUsersError(
      (await detailOf(response)) ?? `Could not load users (HTTP ${response.status}).`,
    );
  }
  return (await response.json()) as AdminAccount[];
}

/** Admin: delete an account by id. Resolves on 204; rejects (with the API's message) otherwise. */
export async function deleteAdminUser(apiBaseUrl: string, userId: string): Promise<void> {
  let response: Response;
  try {
    response = await authedFetch(`${apiBaseUrl}/api/admin/users/${userId}`, { method: "DELETE" });
  } catch (cause) {
    throw new AdminUsersError("Could not reach the user service.", { cause });
  }
  if (!response.ok) {
    throw new AdminUsersError(
      (await detailOf(response)) ?? `Could not delete the account (HTTP ${response.status}).`,
    );
  }
}
