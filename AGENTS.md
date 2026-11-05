# whatsnext

A shared plan (a PLAN.md checklist), check-offs and resumable task progress for every coding agent in a project. Python 3.9+, standard library only. Standalone (ADR-0001).

## Start of every session (read in this order, stop when you have enough)

1. The active task's progress file in `docs/project/progress/`: current state and the exact next action.
2. `docs/decisions/`: accepted and proposed decisions.
3. `docs/project/PLAN.md`: the plan checklist, when the project has one.
4. `README.md`: what the plugin does and how to run its tests.

## Rules

- Standard library only. Keep Python 3.9+ compatible.
- Keep this file under 30 lines. Put changing state in the active task's progress file.
- Record a material decision as `docs/decisions/ADR-NNNN-slug.md` with the decision date in UTC. An agent's suggestion stays `proposed` until the user accepts it.
- Show example times in UTC, for example 23:58Z.
- Local only: do not push, and do not create a remote repository, without asking.
- Run the tests before you report work done: `python3 -m unittest discover -s tests`.
