import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import type { Session, User } from "@supabase/supabase-js";

import { clearCoverViews } from "./coverViewCache";
import { clearLibraryCache } from "./libraryCache";
import { LAST_PRODUCT_KEY, type Product } from "../lib/product";
import { supabase } from "../lib/supabase";

/** Result of a sign-up: a session means immediate login; otherwise the user must confirm by email. */
export interface SignUpResult {
  needsConfirmation: boolean;
}

interface AuthState {
  /** Whether login is required — true only when a Supabase client is configured at build time. */
  enabled: boolean;
  /** True while the initial session is being restored (avoids a flash of the login screen). */
  loading: boolean;
  session: Session | null;
  user: User | null;
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (email: string, password: string, inviteCode?: string) => Promise<SignUpResult>;
  signOut: () => Promise<void>;
  /** Persist the account's display name to Supabase user_metadata (read via resolveDisplayName). */
  updateDisplayName: (displayName: string) => Promise<void>;
  /** Persist the product the account last used, so the next sign-in skips the gateway (read via
   *  resolveLastProduct). Mirrors updateDisplayName — same metadata store, same refresh path. */
  updateLastProduct: (product: Product) => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

function unconfigured(): never {
  throw new Error("Authentication is not configured");
}

/** Persist a patch onto the signed-in account's Supabase `user_metadata`.
 *
 *  `updateUser` emits a USER_UPDATED event, which the provider's onAuthStateChange listener picks
 *  up to refresh the session — so a written field flows to the surfaces that read it (the account
 *  row, the greeting, the product fork) without a reload. Every metadata write goes through here so
 *  that refresh behaviour, and the unconfigured-auth guard, cannot differ between fields. */
async function writeUserMetadata(patch: Record<string, unknown>): Promise<void> {
  if (!supabase) unconfigured();
  const { error } = await supabase.auth.updateUser({ data: patch });
  if (error) throw error;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const enabled = supabase !== null;
  const [loading, setLoading] = useState(enabled);
  const [session, setSession] = useState<Session | null>(null);

  useEffect(() => {
    if (!supabase) return;
    let active = true;
    supabase.auth.getSession().then(({ data }) => {
      if (!active) return;
      setSession(data.session);
      setLoading(false);
    });
    const { data: authListener } = supabase.auth.onAuthStateChange((_event, next) => {
      setSession(next);
    });
    return () => {
      active = false;
      authListener.subscription.unsubscribe();
    };
  }, []);

  // Drop the cross-navigation caches whenever the account changes, so a sign-out / account switch
  // never flashes the previous user's courses (or serves their cover exchanges) before their own
  // library loads.
  const userId = session?.user?.id ?? null;
  useEffect(() => {
    clearLibraryCache();
    clearCoverViews();
  }, [userId]);

  const value = useMemo<AuthState>(
    () => ({
      enabled,
      loading,
      session,
      user: session?.user ?? null,
      signIn: async (email, password) => {
        if (!supabase) unconfigured();
        const { error } = await supabase.auth.signInWithPassword({ email, password });
        if (error) throw error;
      },
      signUp: async (email, password, inviteCode) => {
        if (!supabase) unconfigured();
        // Send the confirmation link back to THIS origin (prod / dev / localhost), not the
        // project's default Site URL. supabase-js (detectSessionInUrl) then parses the returned
        // #access_token and establishes the session. The origin must be in the project's redirect
        // allow-list (Auth → URL Configuration) or Supabase falls back to the Site URL.
        //
        // The invite code rides as user metadata: the Before-User-Created auth hook reads
        // `user_metadata.invite_code` server-side and rejects the signup if it doesn't match the
        // shared code. Sending it here is necessary but NOT the gate — the hook is (a form-only
        // check would be bypassable against the public anon key).
        const { data, error } = await supabase.auth.signUp({
          email,
          password,
          options: {
            emailRedirectTo: window.location.origin,
            ...(inviteCode ? { data: { invite_code: inviteCode } } : {}),
          },
        });
        if (error) throw error;
        return { needsConfirmation: data.session === null };
      },
      signOut: async () => {
        await supabase?.auth.signOut();
      },
      updateDisplayName: (displayName) => writeUserMetadata({ display_name: displayName }),
      updateLastProduct: (product) => writeUserMetadata({ [LAST_PRODUCT_KEY]: product }),
    }),
    [enabled, loading, session],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
