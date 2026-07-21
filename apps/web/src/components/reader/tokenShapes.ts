/** The single source of truth for what "looks like a domain/data token" — shared by the R2 chip
 *  detector (`keywordBadges.ts`) and the R4b keyed-list detector (`inlineSeries.ts`) so the two can't
 *  drift (a token badged inline must also be eligible as a keyed-list key, and vice versa). */

/** A token identifier by shape: an internal-digit id (`IL-4`, `Th2`, `ILC2`), an all-caps acronym
 *  (`TSLP`, `DNA` — capped at 5 so ordinary words like `GETTING` don't qualify), or a mixed-case token
 *  (`IgE`, `mRNA`, `pH`). Excludes the hyphenated number-unit (`600-eosinophil`), which R2 adds on its
 *  own since it isn't a valid sentence-leading key. */
export const TOKEN_ID =
  "[A-Z][A-Za-z]*-?\\d[\\dA-Za-z]*" + // internal-digit id: IL-4, IL-33, Th2, ILC2, CO2, T2
  "|[A-Z]{3,5}" + // all-caps acronym: TSLP, DNA, ICS
  "|[A-Za-z]*[a-z][A-Z][A-Za-z0-9]*"; // mixed-case token: IgE, mRNA, pH, IPv4

/** All-caps English words that read as emphasis, not acronyms — excluded from the acronym shape (R2)
 *  and from keyed-list keys (R4b), so "NEVER skip…" / "ONLY then…" prose isn't mistaken for tokens.
 *  All entries are ≤5 letters, the reach of the `[A-Z]{3,5}` acronym rule. */
export const STOP_TOKENS = new Set([
  "THE", "AND", "BUT", "FOR", "NOT", "YOU", "ARE", "ALL", "ANY", "CAN", "HAS", "HOW", "WHY", "WHO",
  "WAS", "USE", "NOW", "OUR", "OUT", "ONE", "TWO", "VERY", "MUST", "ONLY", "ALSO", "THIS", "THAT",
  "WITH", "FROM", "INTO", "THAN", "THEN", "THEY", "WHEN", "EACH", "MORE", "SOME", "WHAT", "YES",
  "NEVER", "HERE", "THERE", "THESE", "THOSE", "WILL", "WOULD",
]);
