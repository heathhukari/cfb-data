# Player Model: weekly run

The Player Model ("PM") is a shadow model. It never changes Claude's picks; it is graded against Claude's model and Vegas every week.

## Sunday (automatic, GitHub Actions)
`.github/workflows/cfbd.yml` runs every Sunday at 14:23 UTC. It finds the last completed week from CFBD's schedule and pulls
season player stats, usage, PPA, team advanced stats, havoc, lines, games (with finals) and that week's per-game data:
about 12 calls of the free tier's 1,000 a month (plus garbage-time-filtered advanced stats and team box stats for the Data Rating, and once a season the roster talent and last season's final SP+ for its prior). Data lands in `data/<year>/raw/` and is committed by the workflow.
Manual run: Actions → CFBD collect → Run workflow → tick "weekly".

## Monday (the "CFB game insights + last-week recaps" scheduled task, step 11)
Inputs come from the dashboard database after the 9:47 AM update: `top25/<id>`, `predictions/<id>`, and the `teams`
array from the stored pullTeams script; injuries come from Covers (`collect/covers_injuries.js`).

```
git pull
python model/build_inputs.py <year> <week> teams.json top25.json predictions.json   # -> data/<year>/claude_wNN.json
python model/injuries.py covers_raw.json data/<year>/injuries_wNN.json "Covers.com, <date>"
python model/player_model.py <year> <week> data/<year>/injuries_wNN.json            # -> model/out/playermodel_<year>_wNN.json
python model/grade.py <year> <week-1>                                                # grades last week, -> model/out/pm_record_<year>.json
```
Then: dashboard doc `playermodel/<year>-w<week-1>` gets its graded `games`; the new doc `playermodel/<year>-w<week>` is the
model output plus `record` (contents of pm_record_<year>.json). Commit and push `data/` and `model/out/`.

## Model
v2 (Oct 9, 2026): PM = 0.6 x Claude Power + 0.4 x Data Rating (`model/data_rating.py`, coefficients in `model/out/rr_coefs.json`) + QB and injury adjustments.
Research that chose the Data Rating: `model/research.py` (builds as-of-week features) and `model/research_eval.py`
(writes `model/out/research_2024train_2025test.txt` and the dashboard summary `model/out/research_summary.json`).
To refit after a new season: add the season to research.py/research_eval.py, rerun both, and commit the new rr_coefs.json.
