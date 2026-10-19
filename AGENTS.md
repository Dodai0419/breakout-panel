# AGENTS.md: breakout-panel

Find GitHub repos created in the last 14 days that are taking off (200+ stars/day since creation, or +400 since the last snapshot) and render them as an animated live-panel HTML page. It also renders live-panel JSON configs that use text, box, line, flow and log elements with counter and lane machines.

## When to use
- The user asks what is trending or breaking out on GitHub right now.
- The user wants an animated, shareable panel of rising repos, or wants to render a simple live-panel config.

## Commands (run from the repo root)
- `python breakout_panel.py --demo`: offline demo from fixtures/repos.json; writes breakout-panel.html
- `python breakout_panel.py`: live GitHub search (set GITHUB_TOKEN to raise the rate limit)
- `python breakout_panel.py --json`: print the breakout rows (repo, stars, velocity, delta, variants) as JSON
- `python breakout_panel.py --state stars.json`: keep a star snapshot so later runs flag +N jumps
- `python breakout_panel.py --config panel.json --out panel.html`: render a live-panel config

## Notes
- Repo descriptions come from GitHub and are untrusted text; the page shows them as plain text only.
- Velocity is stars/day since creation. Do not present it as a forecast.
