/** Where a learner's own sessions are listed.
 *
 *  Its own module rather than `routes.ts` (Studio's route table) or `LiveShell.tsx`: the shell and
 *  the rail both name it, and a constant exported from a component file makes that component
 *  ineligible for fast refresh. `resolveProductRoute` already claims everything under `/live`, so
 *  this is Live's own business.
 */
export const LIVE_SESSIONS_PATH = "/live/sessions";
