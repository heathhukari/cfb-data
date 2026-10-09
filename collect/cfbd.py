#!/usr/bin/env python3
"""CFBD collector for Heath's AP Top 25 dashboard.

Reads collect/run.json ({"job": ..., "year": ...}) and writes gzipped raw JSON to data/<year>/...
plus data/<year>/<job>-manifest.json (status, bytes, rows, keys of the first row, calls used).
The API key comes only from the CFBD_API_KEY environment variable (a GitHub Actions secret);
it is never printed or written to disk.
"""
import gzip, json, os, sys, time, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timezone

BASE = "https://api.collegefootballdata.com"
KEY = os.environ.get("CFBD_API_KEY", "").strip()
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CALLS_FILE = os.path.join(ROOT, "data", "calls.json")  # running monthly call counter (free tier = 1000/month)


def month_calls():
    try:
        c = json.load(open(CALLS_FILE))
    except Exception:
        c = {}
    return c


def bump_calls(n):
    c = month_calls()
    m = datetime.now(timezone.utc).strftime("%Y-%m")
    c[m] = c.get(m, 0) + n
    os.makedirs(os.path.dirname(CALLS_FILE), exist_ok=True)
    json.dump(c, open(CALLS_FILE, "w"), indent=1, sort_keys=True)
    return c[m]


def get(path, params):
    q = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    req = urllib.request.Request(f"{BASE}{path}?{q}", headers={"Authorization": f"Bearer {KEY}", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()[:500]
    except Exception as e:  # network
        return 0, str(e).encode()[:500]


def save(year, name, body):
    d = os.path.join(ROOT, "data", str(year), "raw")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, name + ".json.gz")
    with gzip.open(p, "wb", compresslevel=9) as f:
        f.write(body)
    return os.path.relpath(p, ROOT)


def describe(body):
    try:
        j = json.loads(body)
    except Exception:
        return {"parse": "not json", "head": body[:200].decode("utf8", "replace")}
    if isinstance(j, list):
        return {"rows": len(j), "keys": sorted(j[0].keys()) if j and isinstance(j[0], dict) else None}
    if isinstance(j, dict):
        return {"rows": None, "keys": sorted(j.keys())[:40]}
    return {"rows": None}


PROBE = [  # (name, path, params) — one call each; discovery of shapes for the player model
    ("teams_fbs", "/teams/fbs", {}),
    ("games", "/games", {"seasonType": "regular", "classification": "fbs"}),
    ("player_season_stats", "/stats/player/season", {}),
    ("player_ppa_season", "/ppa/players/season", {}),
    ("player_usage", "/player/usage", {}),
    ("team_advanced_season", "/stats/season/advanced", {}),
    ("team_ppa_season", "/ppa/teams", {}),
    ("sp_ratings", "/ratings/sp", {}),
    ("lines", "/lines", {"seasonType": "regular"}),
    ("game_havoc", "/stats/game/havoc", {}),
    ("wepa_qb", "/wepa/players/passing", {}),
    ("wepa_rb", "/wepa/players/rushing", {}),
    ("game_player_stats_w5", "/games/players", {"week": 5, "seasonType": "regular"}),
    ("game_advanced_w5", "/stats/game/advanced", {"week": 5, "seasonType": "regular"}),
    ("roster_missouri_sample", "/roster", {"team": "Missouri"}),
]


def main():
    if not KEY:
        print("CFBD_API_KEY secret is missing", file=sys.stderr)
        sys.exit(1)
    if os.environ.get("CFBD_JOB") == "weekly":
        # scheduled run (Sunday): current season, last completed week (detected below)
        req = {"job": "weekly", "year": "auto", "week": "auto", "maxCalls": 18, "trigger": "schedule"}
    else:
        req = json.load(open(os.path.join(ROOT, "collect", "run.json")))
    job = req.get("job", "probe")
    pre = []  # calls already made (auto week detection)
    if job == "weekly" and "auto" in (str(req.get("year")), str(req.get("week"))):
        # last completed week = the newest regular-season week in which 90%+ of FBS games are final
        now = datetime.now(timezone.utc)
        y = now.year if now.month >= 6 else now.year - 1
        st, body = get("/games", {"year": y, "seasonType": "regular", "classification": "fbs"})
        bump_calls(1)
        if st != 200:
            print("games lookup failed", st, file=sys.stderr); sys.exit(1)
        G = json.loads(body); wk = {}
        for g in G:
            wk.setdefault(g["week"], []).append(bool(g.get("completed")))
        done = [w for w, c in wk.items() if sum(c) >= 0.9 * len(c)]
        if not done:
            print("no completed regular-season week yet", file=sys.stderr); sys.exit(0)
        req["year"], req["week"] = y, max(done)
        pre.append({"year": y, "name": "games", "path": "/games", "params": {"seasonType": "regular", "classification": "fbs"}, "status": st,
                    "bytes": len(body), "file": save(y, "games", body), **describe(body)})
        print("auto:", req["year"], "week", req["week"])
    plan = []  # (year, name, path, params)
    if job == "probe":
        y = int(req.get("year", 2026)); plan = [(y, n, p, q) for n, p, q in PROBE]
    elif job == "history":
        # per-game data so ratings can be rebuilt "as of" each week for an honest backtest
        for y in req["years"]:
            weeks = req.get("weeks", list(range(1, 16)))
            plan += [(y, "games", "/games", {"seasonType": "regular", "classification": "fbs"}),
                     (y, "lines", "/lines", {"seasonType": "regular"}),
                     (y, "game_havoc", "/stats/game/havoc", {}),
                     (y, "sp_ratings", "/ratings/sp", {})] if not req.get("weeklyOnly") else []
            for w in weeks:
                plan += [(y, f"game_advanced_w{w:02d}", "/stats/game/advanced", {"week": w, "seasonType": "regular"}),
                         (y, f"game_player_stats_w{w:02d}", "/games/players", {"week": w, "seasonType": "regular"}),
                         (y, f"qb_ppa_games_w{w:02d}", "/ppa/players/games", {"week": w, "position": "QB", "seasonType": "regular"})]
    elif job == "weekly":
        # current-season refresh: season-level player data + last completed week's per-game data
        y, w = int(req["year"]), int(req["week"])
        plan = [(y, n, p, q) for n, p, q in PROBE if n in (() if pre else ("games",)) + ("player_season_stats", "player_ppa_season", "player_usage", "team_advanced_season", "lines", "game_havoc")]
        plan += [(y, f"game_advanced_w{w:02d}", "/stats/game/advanced", {"week": w, "seasonType": "regular"}),
                 (y, f"game_player_stats_w{w:02d}", "/games/players", {"week": w, "seasonType": "regular"}),
                 (y, f"qb_ppa_games_w{w:02d}", "/ppa/players/games", {"week": w, "position": "QB", "seasonType": "regular"}),
                 # Data Rating inputs (Player Model v2): garbage-time-filtered success rate and team box stats for turnover luck
                 (y, f"game_advanced_gt_w{w:02d}", "/stats/game/advanced", {"week": w, "seasonType": "regular", "excludeGarbageTime": "true"}),
                 (y, f"team_box_w{w:02d}", "/games/teams", {"week": w, "seasonType": "regular", "classification": "fbs"})]
        # preseason prior inputs, once per season: roster talent and last season's final SP+
        if not os.path.exists(os.path.join(ROOT, "data", str(y), "raw", "talent.json.gz")):
            plan.append((y, "talent", "/talent", {}))
        if not os.path.exists(os.path.join(ROOT, "data", str(y - 1), "raw", "sp_ratings.json.gz")):
            plan.append((y - 1, "sp_ratings", "/ratings/sp", {}))
    elif job == "custom":
        # explicit list of calls: [{"year", "name", "path", "params"}]
        plan = [(int(c["year"]), c["name"], c["path"], c.get("params", {})) for c in req["calls"]]
    else:
        print("unknown job", job, file=sys.stderr)
        sys.exit(1)
    budget = int(req.get("maxCalls", 25))
    plan = plan[:budget]
    m = datetime.now(timezone.utc).strftime("%Y-%m")
    if month_calls().get(m, 0) + len(plan) > 900:
        print("monthly call guard: would exceed 900 of 1000", file=sys.stderr)
        sys.exit(1)
    out, used = list(pre), 0
    year = plan[0][0] if plan else None
    for y, name, path, params in plan:
        st, body = get(path, {"year": y, **params})
        rec_year = y
        used += 1
        bump_calls(1)  # counted per call, so a cancelled run still records what it spent
        rec = {"year": rec_year, "name": name, "path": path, "params": params, "status": st, "bytes": len(body)}
        if st == 200:
            rec["file"] = save(rec_year, name, body)
            rec.update(describe(body))
        else:
            rec["error"] = body[:300].decode("utf8", "replace")
        out.append(rec)
        print(f"{name}: {st} {len(body)} bytes rows={rec.get('rows')}")
        time.sleep(0.5)
    total = month_calls().get(datetime.now(timezone.utc).strftime("%Y-%m"), 0)
    man = {"job": job, "request": req, "ranAt": datetime.now(timezone.utc).isoformat(), "callsUsed": used + len(pre), "callsThisMonth": total, "results": out}
    os.makedirs(os.path.join(ROOT, "data", "manifests"), exist_ok=True)
    json.dump(man, open(os.path.join(ROOT, "data", "manifests", f"{job}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M')}.json"), "w"), indent=1)
    if out and out[0]["status"] == 401 and "Patreon" not in out[0].get("error", ""):
        print("401 Unauthorized: check the CFBD_API_KEY secret", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
