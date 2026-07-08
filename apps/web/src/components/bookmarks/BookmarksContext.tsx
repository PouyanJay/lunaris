import { createContext, useContext, useMemo, type ReactNode } from "react";

import { useBookmarks, type BookmarksState } from "../../hooks/useBookmarks";
import type { BookmarkDraft, BookmarkRef } from "../../lib/bookmarks";

interface BookmarksApi {
  /** Whether saving is possible at all (a provider with an API is mounted). */
  enabled: boolean;
  /** Whether membership is known (list loaded) — toggles stay disabled until truth arrives. */
  ready: boolean;
  state: BookmarksState;
  reload: () => void;
  isSaved: (ref: BookmarkRef) => boolean;
  toggle: (draft: BookmarkDraft) => void;
}

// Default: disabled + inert — an affordance rendered outside a provider (offline SeedApp,
// isolated tests) simply shows no bookmark button rather than crashing.
const BookmarksContext = createContext<BookmarksApi>({
  enabled: false,
  ready: false,
  state: { status: "loading" },
  reload: () => {},
  isSaved: () => false,
  toggle: () => {},
});

/** Read the ambient bookmarks capability. A context module pairs its hook with its provider, so
 *  the fast-refresh "only export components" hint doesn't apply here. */
// eslint-disable-next-line react-refresh/only-export-components
export function useBookmarksApi(): BookmarksApi {
  return useContext(BookmarksContext);
}

interface BookmarksProviderProps {
  apiBaseUrl: string;
  children: ReactNode;
}

/** One bookmarks instance for the whole studio: every affordance (reader header, KC inspector,
 *  claim cards) and the Bookmarks screen share membership, so a save made anywhere is pressed
 *  everywhere without refetching per site. */
export function BookmarksProvider({ apiBaseUrl, children }: BookmarksProviderProps) {
  const { state, reload, isSaved, toggle } = useBookmarks(apiBaseUrl);
  const value = useMemo<BookmarksApi>(
    () => ({
      enabled: Boolean(apiBaseUrl),
      ready: state.status === "ready",
      state,
      reload,
      isSaved,
      toggle,
    }),
    [apiBaseUrl, state, reload, isSaved, toggle],
  );
  return <BookmarksContext.Provider value={value}>{children}</BookmarksContext.Provider>;
}
