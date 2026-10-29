# Suprio TV — GitHub Pages + scheduled health checks

## Files
- `index.html`: public TV-style website/player.
- `sources.json`: M3U playlist URLs and health settings.
- `scripts/check_streams.py`: parses, deduplicates, and probes streams.
- `.github/workflows/refresh.yml`: scheduled/manual GitHub Action.
- `data/channels.json`: generated website catalog.
- `data/health-state.json`: consecutive-failure history.

## Phone-only setup
1. Create/open your GitHub repository in a mobile browser.
2. Add these files at the exact paths shown above; create folders as needed.
3. Commit all files to the default branch (normally `main`).
4. Open **Actions**. If GitHub asks, enable Actions.
5. Select **Refresh Suprio TV channels** → **Run workflow**. Wait for it to finish.
6. Open **Settings → Pages**; choose **Deploy from a branch**, select `main` and `/(root)`, then Save.
7. Open the published Pages URL after the first workflow succeeds.

## Add more playlists
Edit `sources.json` and add each public M3U URL to `playlists`, separated by commas. Commit the change, then run the workflow manually. The scheduled workflow runs twice per hour.

## Health rules
- Working: at least one stream passes a server-side request check in that run.
- Unverified: checks fail but the repeated-failure threshold is not reached.
- Maintenance: all listed backups fail for 3 consecutive successful playlist-refresh runs; change `maintenance_after_consecutive_failed_runs` to adjust the threshold.
- If every playlist fetch fails, old entries/statuses are preserved rather than demoted because the playlist fetch itself failed.

A server-side request check cannot guarantee playback for every visitor. Geo-blocking, anti-bot protections, codecs, CORS, transient failures, and regional restrictions can cause false results. HLS checks try to fetch the manifest and one child playlist/segment when practical. GitHub Actions is free within GitHub's usage limits; a very large playlist may take time or hit rate limits.

## Public repository warning
Files committed to a public repo are public, including playlist URLs and stream URLs. Do not commit URLs containing passwords, tokens, or private credentials. Only use streams you are authorized to access and redistribute.
