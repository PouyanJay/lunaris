/** Recognised domain keywords that read better as a labelled chip than as inline text. HTTP request
 *  methods are the first set: a closed, conventional vocabulary whose semantics (read / create /
 *  replace / remove) a colour-coded-but-labelled badge can convey at a glance. The meaning lives in
 *  the word AND the category — never colour alone (WCAG). Shared by the render-side detection rule
 *  (`keywordBadges`) and the `KeywordBadge` component. */
export const KEYWORD_META: Record<string, { category: string; title: string }> = {
  GET: { category: "read", title: "HTTP GET — retrieve a resource" },
  POST: { category: "create", title: "HTTP POST — submit or create" },
  PUT: { category: "replace", title: "HTTP PUT — replace a resource" },
  PATCH: { category: "update", title: "HTTP PATCH — partially update" },
  DELETE: { category: "delete", title: "HTTP DELETE — remove a resource" },
  HEAD: { category: "meta", title: "HTTP HEAD — headers only" },
  OPTIONS: { category: "meta", title: "HTTP OPTIONS — supported methods" },
};
