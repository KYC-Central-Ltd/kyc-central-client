---
name: delegate-to-cheaper-models
description: Use when an expensive model (Opus) faces bulk, mechanical, or well-specified work — repetitive multi-file edits, boilerplate, test scaffolding, search-and-summarize, mechanical refactors, data munging. Delegates the grunt work to cheaper models (Haiku/Sonnet) via subagents and keeps the expensive model only for planning, specifying, and reviewing — cutting token cost.
---

# Delegate to cheaper models

Keep the expensive orchestrator model for judgment (planning, specifying, reviewing) and push mechanical execution to cheaper models via subagents. This cuts cost without sacrificing quality — provided the spec is explicit and the output is verified.

## When to use

Delegate to a cheaper model when the work is **mechanical and well-specified**:
- Repetitive edits applying the same pattern across many files
- Boilerplate, scaffolding, test stubs
- Search-and-summarize / inventory tasks
- Mechanical refactors (rename, move, reformat)
- Data munging / file generation from a clear template

Do NOT delegate genuinely hard work that needs the strong model: novel design, subtle debugging, ambiguous requirements, security-sensitive logic.

## How

1. **Stay on the expensive model to plan and write the spec.** The spec must name exact files, the exact transformation, and acceptance criteria. Ambiguity is what makes cheap models drift.
2. **Dispatch a subagent with a cheaper model** using the Agent tool's `model` parameter:
   - `model: "haiku"` — cheapest; use for mechanical, high-volume work.
   - `model: "sonnet"` — mid; use when light judgment is needed.
   - Keep the orchestrator (Opus) as planner/reviewer only.
3. **Review before accepting.** Always verify the subagent's output — run tests, `grep`, or inspect the diff. Never accept unseen.
4. **Parallelize independent work.** For 2+ independent tasks with no shared state, dispatch several cheap subagents at once: use the `superpowers:dispatching-parallel-agents` skill if it is installed; otherwise issue all the Agent calls in a single message.

## Model picker

| Work | Model |
|------|-------|
| Mechanical / high-volume / well-specified | Haiku |
| Needs a little judgment | Sonnet |
| Planning, specifying, reviewing | Opus (orchestrator) |

## Discipline

The savings only hold if the spec is explicit and you verify the result. A vague prompt to a cheap model produces work you have to redo on the expensive model — losing the savings. Spec tightly, review always.
