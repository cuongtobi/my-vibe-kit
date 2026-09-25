# Lightweight frontend policy

Use this reference only when the current task is frontend work. The runtime may expose this as `relevant-context.json -> frontend.enabled`. When runtime classification is unavailable, apply it only when the requested or affected files clearly belong to a user interface.

This policy augments the existing `vibe -> plan -> build -> verify` flow. It does not create a new command, skill, artifact type, browser engine, or design runtime.

## Preserve versus redesign

- Refinement preserves the existing visual language, behavior, copy, interaction model, and unrelated UI. Do not turn a spacing, responsiveness, or component fix into a redesign.
- Redesign may replace the visual language inside the accepted scope, but preserve product behavior, content truth, navigation/user flow, data contracts, and accessibility expectations unless the request explicitly changes them.
- Never invent marketing claims, fake data, or product behavior to make a screen look more complete.

## Design context

- DESIGN.md is optional. If it exists, read it as durable visual guidance for the affected surface.
- If DESIGN.md is absent, infer the incumbent design system from bounded relevant context: theme/tokens, CSS variables, Tailwind/theme config, shared UI components, layout primitives, fonts, spacing, and nearby screens.
- Do not generate DESIGN.md merely because it is missing.
- Existing project conventions win over generic aesthetic preferences unless the task explicitly asks for a redesign.

## Surface priority

Use the runtime surface hint as a lightweight priority, not as a new architecture:

- `marketing`: hierarchy, identity, clarity, and action.
- `application`: task completion, scanability, consistency, and state clarity.
- `content`: readability, typography, navigation, and long-form rhythm.
- `commerce`: product/price/action clarity, trust, and error/empty/loading states.
- `admin`: information density, predictable controls, and efficient scanning.
- `component`: local consistency and reusable behavior without changing surrounding screens.

## Frontend quality floor

When relevant to the change:

- Reuse existing components, tokens, icons, and interaction patterns before creating parallel ones.
- Keep semantic HTML and accessible names/labels. Preserve keyboard and focus behavior.
- Cover loading, error, empty, disabled, hover, focus, and selected states only when the affected interaction can actually enter those states.
- Treat mobile/responsive behavior as part of the implementation, not a later rewrite.
- Avoid accidental horizontal overflow, clipped text, broken long content, or layout assumptions that only work for demo copy.
- Avoid unnecessary wrappers, card-in-card composition, decorative effects, gradients, or motion without a product/design reason.
- Keep business logic outside presentational components when existing framework/project boundaries support that separation.
- Do not add a frontend package solely to solve a task that existing project capabilities can handle.

## Acceptance dimensions

Plan and verify the dimensions that are materially relevant:

1. `visual-consistency`
2. `responsive-behavior`
3. `interaction-states`
4. `accessibility`
5. `content-layout-integrity`

These are acceptance dimensions, not five mandatory new tests. Reuse existing tests, component stories, browser checks, screenshots, or focused manual evidence. If a dimension is not applicable, do not invent work for it; state why in the plan/evidence when that matters.

## Visual verification

- Prefer project-native browser/E2E/story/screenshot tooling when it already exists.
- Do not install Playwright, Cypress, a browser extension, or another visual runtime merely because this policy is active.
- Use at most one primary visual inspection round and one confirmation round for the same frontend change. Batch findings before editing instead of entering an open-ended polish loop.
- When browser/visual verification is unavailable, report that limitation and rely on the strongest available static/runtime evidence. Do not claim visual behavior was verified.
