/** Turn CopilotKit's anonymous telemetry off before the runtime loads.
 *
 *  The runtime opts *in* by default and announces it on boot. This is a self-hosted service running
 *  inside somebody's Azure subscription and handling a learner's session traffic, so phoning a
 *  third party home is not a default we should inherit silently. Set here rather than in the
 *  Dockerfile alone, so it also holds for `npm run dev` and for the tests.
 *
 *  Imported for its side effect, and imported FIRST — ESM evaluates a module's imports in source
 *  order, so this runs before `@copilotkit/runtime` reads the variable. An assignment inside
 *  `main.ts` would be hoisted below the runtime import and arrive too late.
 *
 *  `??=` so an operator who genuinely wants telemetry can still opt back in from the environment.
 */
process.env.COPILOTKIT_TELEMETRY_DISABLED ??= "true";
