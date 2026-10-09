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
    req = json.load(open(os.path.join(ROOT, "collect", "run.json")))
    job, year = req.get("job", "probe"), int(req.get("year", 2026))
    if job != "probe":
        print("unknown job", job, file=sys.stderr)
        sys.exit(1)
    budget = int(req.get("maxCalls", 25))
    if month_calls().get(datetime.now(timezone.utc).strftime("%Y-%m"), 0) + len(PROBE) > 900:
        print("monthly call guard: would exceed 900 of 1000", file=sys.stderr)
        sys.exit(1)
    out, used = [], 0
    for name, path, params in PROBE[:budget]:
        st, body = get(path, {"year": year, **params})
        used += 1
        rec = {"name": name, "path": path, "params": params, "status": st, "bytes": len(body)}
        if st == 200:
            rec["file"] = save(year, name, body)
            rec.update(describe(body))
        else:
            rec["error"] = body[:300].decode("utf8", "replace")
        out.append(rec)
        print(f"{name}: {st} {len(body)} bytes rows={rec.get('rows')}")
        time.sleep(1)
    total = bump_calls(used)
    man = {"job": job, "year": year, "ranAt": datetime.now(timezone.utc).isoformat(), "callsUsed": used, "callsThisMonth": total, "results": out}
    json.dump(man, open(os.path.join(ROOT, "data", str(year), f"{job}-manifest.json"), "w"), indent=1)
    if any(r["status"] == 401 for r in out):
        print("401 Unauthorized: check the CFBD_API_KEY secret", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
