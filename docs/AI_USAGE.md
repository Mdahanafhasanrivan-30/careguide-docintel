# AI-assisted development log

| Date | Tool | What I asked for | What I kept / changed |
| --- | --- | --- | --- |
| 2026-11-22 | Claude (chat) | Project roadmap, phase breakdown, Phase 0 guide | Followed the phase plan; typed and checked the code myself and tested each step |
| 2026-11-23 | Claude (chat) | Help fixing Windows Update because it was stuck for 20 days, WSL and Docker setup, and a missing `packaging` dependency | Applied the fixes and verified them with the five Phase 0 proofs |


made synthetic data and test cases with AI in all the phases. Also AI helped me to use the ubuntu bashes when needed. I dont memorize them. 

Phase 3 (validation): Claude (Anthropic) wrote the step-by-step guide and the starting code for the validation rules, duplicate checks, test invoices and scripts, and tested it in its own environment. I typed the code, ran it against my data and the real Gemini API, found that prompt v2 misread rows inside the items table (e18), and changed to prompt v3 based on that result.

| 2026-11-25 | Claude (chat) | Phase 4 guide and starting code (DB, API, Celery jobs, tests) | Typed all code myself, ran every checkpoint, debugged the startup and import errors, ran the live batch with real Gemini |

phase 5 testing, debugging, bash commands and code editing.

## Phase 6 — Frontend

- **Tool:** Claude (Anthropic) used as a helper and guide.
- **What Claude produced:** the step-by-step Phase 6 guide, the frontend code (pages, components, API client, proxy route handler), the two backend endpoints with their tests, and the first draft of my Phase 6 notes, written from results I reported.
- **What I did:** created every file in my repo, ran the containers and tests, and checked each checkpoint in the browser. I debugged the problems myself with Claude's help: a port conflict on 3000 (moved to 3001) and a page saved in the wrong folder (a 404 on /documents). I reviewed the notes against what I had actually seen.
- **How I checked the output:** 235 backend tests pass, every screen was tested by hand against real documents, and I checked the inv_009 total mismatch by hand (1032.40 + 51.62 = 1084.02, not 1094.02).