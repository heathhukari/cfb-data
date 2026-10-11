Add this week's Josh Pate polls to Heath's CFB Top 25 dashboard artifact (https://claude.ai/artifact/3xNnYRHpv5kim7XRkquRdn) for the "Polls compared" section, then refresh Claude's BCS with the new Commissioner's Poll. Claude's Top 25 is poll-free (a locked pre-AP ballot): never rerun or rewrite top25.

Data layout:
- The "Polls compared" section reads the collection "altpolls", one doc per AP week. The doc id is the newest "polls" doc id (e.g. 2026-w07).
- Doc shape: {season, week, sortKey, label, updatedAt, polls: [{key, name, by, kind, edition ("Week N"), stale (true when the edition is older than P's week), note, date, url, status ("ok" | "missing"), teams: [{rank, team}]}]}.
- JP Poll entry: key "jp", name "JP Poll", kind "Power rating", note "Josh Pate's power ratings — who he'd favor on a neutral field, not a résumé ranking (\"Power ratings are not rankings\")."
- Commissioner's Poll entry: key "commissioner", name "Commissioner's Poll", kind "Ranking", note "Josh Pate's weekly Top 25 ranking." When it's stale, the note says which edition it is and that it came out before the latest games.

Team names must be the dashboard's names: "Miami (FL)", "Ole Miss", "Pittsburgh" (his graphics say "Pitt"), "USC", "BYU", and full "State" names. A maroon interlocking "MSU" logo is Mississippi State; Michigan State's logo is green. Copy names from the newest polls doc where possible.

Where the polls are: both are image posts by @JoshPateCFB on X. The JP Poll post reads "🚨JP POLL: Week N Edition🚨" and usually goes up Monday or Tuesday. The Commissioner's Poll post reads "🚨WEEK N COMMISSIONER'S POLL🚨" and usually goes up Thursday. A single post page can be read without logging in, but the profile timeline and X search need a login.

1. Load ArtifactData via ToolSearch ("select:ArtifactData"). Load the built-in browser tools with one ToolSearch for the *Claude_Browser__* prefix. Read the newest "polls" doc and call it P. Read altpolls/<P id> if it exists. Keep any poll already "ok" for P's week; only fill polls that are missing or stale.
2. Find each post URL with WebSearch: queries like "JoshPateCFB JP POLL Week N" and "JoshPateCFB Commissioner's Poll Week N site:x.com". Also try On3 or other articles that link or embed the post. If there's no post URL, a dated text article from this week that lists all 25 teams is acceptable. He also posts both on Instagram (@joshpatecfb), sometimes before X; Heath may share a screenshot, in which case the poll is already stored. Otherwise mark the poll missing.
3. Read each image:
   - Open the post in the built-in browser.
   - Run javascript_tool: [...document.querySelectorAll('img')].map(i=>i.src).filter(s=>/pbs.twimg.com\/media/.test(s))
   - Open the first media URL with format=png&name=large and take a screenshot.
   - Read ranks 1-25 from the logos and their numbers, and confirm the edition text on the graphic ("WEEK N EDITION").
   - If a logo is ambiguous, zoom in on it. Never guess. If any rank is still uncertain, set status "missing" and say which rank.
4. Write the altpolls doc with "set", or with "update" plus if_version if it already exists. Set date to the post date and url to the post URL.
5. REFRESH CLAUDE'S BCS only if the Commissioner's Poll changed in this run: read doc code/claude-model, evaluate its rankings text in node in the workspace, call bcsWithCommish(<bcs/<P id> doc>, <new Commissioner's Poll teams>, {edition, date, url}, <now ISO>) and set bcs/<P id> with its if_version. Do not touch top25, outlook, brackets, darkhorses or picks. The JP Poll is display-only.
6. Report in three lines:
   1. Each poll's status, edition and source URL.
   2. The biggest gaps against AP (5+ spots).
   3. Whether Claude's BCS was refreshed, its top 5, and any team that moved 3+ spots.
