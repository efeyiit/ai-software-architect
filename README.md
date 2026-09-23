# Ariadne

Ariadne is a planned developer tool for analyzing a GitHub repository and presenting evidence about its structure, dependencies, quality, tests, security, and architecture. The intended product also includes source linked explanations, diagrams, documentation assistance, and a repository chat.

The name comes from Ariadne's thread through the labyrinth: the intended experience leads each finding back to the source and evidence that explains it.

**Current status: planning.** This repository contains the source design and a task plan. There is no working application, verified analysis result, or product demo yet. Proposed technologies and architecture decisions in the plan are subject to implementation and review.

The [master plan](docs/MASTER-PLAN.md) maps the full design to 39 task cards in [docs/tasks](docs/tasks). [Coverage](docs/COVERAGE.md) tracks the design sections, and [the workflow](docs/WORKFLOW.md) describes how tasks move from implementation through verification. GitHub publication rules are in [docs/GITHUB-WORKFLOW.md](docs/GITHUB-WORKFLOW.md).

The intended safety boundary is to treat analyzed repository content as data, keep evidence separate from AI interpretation, and avoid executing analyzed code by default. These are design requirements, not verified product capabilities.
