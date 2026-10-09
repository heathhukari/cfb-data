"""Build data/<year>/claude_w<NN>.json, the Player Model's link to Claude's model, from three dashboard exports.

Usage: python model/build_inputs.py <year> <week> <teams.json> <top25.json> <predictions.json>
  teams.json        the `teams` array returned by the stored pullTeams script (Monday step 10): [{name, sp, fpi, own, ...}]
  top25.json        doc top25/<id> (ArtifactData get with out_dir)
  predictions.json  doc predictions/<id>
Claude Power = 0.45 x SP+ + 0.35 x FPI + 0.20 x own results model (same as the rankings engine).
"""
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W = {"sp": 0.45, "fpi": 0.35, "own": 0.20}


def unwrap(d):
    return d.get("data", d) if isinstance(d, dict) and "data" in d and isinstance(d["data"], dict) else d


def build(year, week, teams, top25, pred):
    power = {}
    for t in teams:
        try:
            power[t["name"]] = round(sum(W[k] * float(t[k]) for k in W), 2)
        except (KeyError, TypeError, ValueError):
            pass
    order = sorted(power, key=lambda n: -power[n])
    t25 = {}
    for t in top25.get("teams", []):
        t25[t["team"]] = {"power": t.get("power"), "powerRk": t.get("powerRk"), "score": t.get("score"), "rank": t.get("rank"),
                          "blendPower": t.get("blendPower"), "apRank": t.get("apRank")}
    games = []
    for g in pred.get("games", []):
        c, v = g.get("claude") or {}, g.get("vegas") or {}
        games.append({"id": str(g["id"]), "home": g["home"], "away": g["away"], "neutral": bool(g.get("neutral")),
                      "claudeHomeMargin": c.get("homeMargin"), "claudeHomeWin": c.get("homeWin"),
                      "vegasHomeSpread": v.get("homeSpread"), "kickoff": g.get("kickoff")})
    return {"season": year, "week": week, "source": f"top25/{year}-w{week:02d} (v{top25.get('version', '?')})",
            "teams": t25, "power": {n: power[n] for n in order}, "games": games}


if __name__ == "__main__":
    y, w = int(sys.argv[1]), int(sys.argv[2])
    teams = json.load(open(sys.argv[3]))
    teams = teams.get("teams", teams) if isinstance(teams, dict) else teams
    doc = build(y, w, teams, unwrap(json.load(open(sys.argv[4]))), unwrap(json.load(open(sys.argv[5]))))
    bad = [k for k, v in doc["teams"].items() if k not in doc["power"]]
    nog = [g["id"] for g in doc["games"] if g["claudeHomeMargin"] is None]
    if len(doc["power"]) < 130 or bad:
        print(f"WARNING: {len(doc['power'])} teams with power; top-25 teams without power: {bad}", file=sys.stderr)
    if nog:
        print(f"note: {len(nog)} games without a Claude line (skipped by the model): {nog}", file=sys.stderr)
    p = os.path.join(ROOT, "data", str(y), f"claude_w{w:02d}.json")
    json.dump(doc, open(p, "w"), separators=(",", ":"))
    print(p, len(doc["power"]), "teams,", len(doc["teams"]), "top-25 entries,", len(doc["games"]), "games")
