# ProcessIQ premium insights design

## Brief and authorization
The user approved the proposed warm, restrained dashboard for small-business owners and explicitly requested autonomous implementation, Git checkpoints/pushes, and a working app preview. Proceed without further design approval gates. Preserve the working CSV, sample, interview, review, analysis, and plan journeys.

## Product
The primary questions are: where does time go, what does labor cost, and what should I try next? This is one representative sequential workflow assessment, not historical operational analytics. Show synthetic provenance, reviewed facts, partial results, and projection assumptions clearly.

## Layout and visual system
Warm ivory #F7F8F5 canvas, white surfaces, graphite #202824 text, forest #315C49 actions, amber #B87928 waiting, gray-green #626D66 supporting text, #E1E6DF borders. Use bundled Geist throughout; Instrument Serif Italic only for editorial accent. Spacious 24px card padding, restrained 16–20px radii, fine borders and soft shadows. Sidebar contains product identity, navigation/context, and secondary source controls. Header names the actual process.

Separate Overview, Workflow, Improvements, and What if workspaces. The Overview has an evidence-derived hero finding; three main metrics; an interactive step breakdown; contextual evidence; and a next-action prompt. Review retains every existing confirmation and validation mechanism. First-use source selection remains clear and optional interview works as before. Saving reviewed data and calculating routes to overview; incomplete workflows remain useful.

## Interactions
Time / effort / cost chart lenses; active/wait/combined time modes; process order or descending contribution; selected step; exact-value table; evidence and formulas. Support chart selection with a keyboard-friendly step selector as an equivalent control. Long workflows require bounded-height scrolling/search. Selected-step detail uses stable IDs even for duplicate names. New derived percentages require complete nonzero denominators and Decimal arithmetic.

What-if is an isolated hypothetical scenario: select a step, reduce active or waiting time by 0–100%, compare baseline and hypothetical values, reset readily. Never mutate or confirm saved facts, affect evidence, generate actual savings claims, or call AI. Preserve per-step cent rounding and missing-input behavior; unavailable inputs must not become zero.

## Trust and resilience
Unknown is distinct from zero, missing from unconfirmed. Preserve partial rankings and ties. Waiting is elapsed time before a step and is not charged as labor. Monthly labor cost is a projection, excluding materials/overhead. Facts edits invalidate calculated results and plans. Live provider calls remain explicit; no credentials committed. User-facing copy describes business concepts, not implementation details.

## Motion and accessibility
Purposeful 120–280ms transitions for entry, focus and controls, no perpetual dashboard animations. Respect reduced motion. Visible keyboard focus, readable contrast, labels alongside color, semantic headings. Responsive layout stacks on narrow screens without clipping charts or controls. Onboarding may retain existing atmospheric interview treatment.

## Verification
Run existing 280 offline tests and new behavior tests; live-provider checks stay opt-in. Verify complete/incomplete samples, editing and recalculation, navigation without losing drafts, offline plans, selected step, scenario isolation/zero/missing facts, and large-workflow chart behavior. Inspect rendered browser desktop and narrow layout. Baseline and tested milestones are committed and pushed to a dedicated private repository under the authenticated user's account.
