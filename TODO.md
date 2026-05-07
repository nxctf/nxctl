# TODO - ngrok token retry + fallback behavior

- [ ] Step 1: Modify `src/scripts/exports/ngrok.py` to try ngrok tokens sequentially (token1..tokenN) when starting a tunnel fails.

- [ ] Step 2: Ensure ngrok reuse/state logic still works, but if reuse fails it should attempt tokens in order.
- [ ] Step 3: Modify `src/scripts/lifecycle.py` so that provider fallback order remains: try ngrok first (with token retry inside provider). Only if all ngrok tokens fail, then proceed to localtunnel.
- [ ] Step 4: Add logging so it’s obvious token #x failed/succeeded.
- [ ] Step 5: Run unit/basic check (import syntax / lint) and a quick `python -m py_compile` on modified files.
