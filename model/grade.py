"""Grade the Player Model's game lines against Claude's model and Vegas once the games are final.

Usage: python model/grade.py <year> <week>
  Reads model/out/playermodel_<year>_w<week>.json and the finals in data/<year>/raw/games.json.gz
  (refreshed by the Sunday CFBD run). Writes a `result` into each graded game of that file and
  recomputes the season record over every graded week, saved to model/out/pm_record_<year>.json.
  Prints the record. Games not yet final keep result null and are picked up by a later run.

Per game: actual home margin; misses for PM, Claude and Vegas (Vegas margin = -home spread); which of
PM / Claude landed closer; and, when PM and Vegas disagree by 3+ points, whether PM's side covered.
"""
import glob, gzip, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "model", "out")


def finals(year):
    p = os.path.join(ROOT, "data", str(year), "raw", "games.json.gz")
    G = json.loads(gzip.open(p).read()) if os.path.exists(p) else []
    return {str(g["id"]): g for g in G if g.get("completed") and g.get("homePoints") is not None}


def grade_week(year, week, F):
    p = os.path.join(OUT, f"playermodel_{year}_w{week:02d}.json")
    doc = json.load(open(p))
    n = 0
    for g in doc.get("games", []):
        f = F.get(str(g["id"]))
        if not f:
            g.setdefault("result", None); continue
        # CFBD lists the same home team as ESPN; check names anyway via the margin sign convention
        m = f["homePoints"] - f["awayPoints"]
        pm, cl, sp = g.get("pmHomeMargin"), g.get("claudeHomeMargin"), g.get("vegasHomeSpread")
        vg = -sp if sp is not None else None
        r = {"final": f"{g['away']} {f['awayPoints']}, {g['home']} {f['homePoints']}", "homeMargin": m,
             "pmErr": round(abs(pm - m), 1) if pm is not None else None,
             "claudeErr": round(abs(cl - m), 1) if cl is not None else None,
             "vegasErr": round(abs(vg - m), 1) if vg is not None else None}
        r["closer"] = None if r["pmErr"] is None or r["claudeErr"] is None else ("tie" if r["pmErr"] == r["claudeErr"] else "pm" if r["pmErr"] < r["claudeErr"] else "claude")
        if pm is not None and vg is not None and abs(pm - vg) >= 3:
            side = 1 if pm > vg else -1          # +1 = PM likes home vs the spread
            cover = (m - vg) * side
            r["pmVsVegas"] = {"side": g["home"] if side > 0 else g["away"], "result": "W" if cover > 0 else "L" if cover < 0 else "P"}
        else:
            r["pmVsVegas"] = None
        g["result"] = r; n += 1
    doc["gradedThrough"] = f"{n}/{len(doc.get('games', []))} games final"
    json.dump(doc, open(p, "w"), separators=(",", ":"))
    return doc, n


def season_record(year):
    rows, weeks = [], []
    for p in sorted(glob.glob(os.path.join(OUT, f"playermodel_{year}_w[0-9][0-9].json"))):
        d = json.load(open(p))
        g = [x for x in d.get("games", []) if x.get("result")]
        if g: weeks.append(d["week"]); rows += g
    if not rows:
        return None
    mean = lambda k: round(sum(x["result"][k] for x in rows if x["result"][k] is not None) / max(1, sum(x["result"][k] is not None for x in rows)), 2)
    cl = [x["result"]["closer"] for x in rows]
    ats = [x["result"]["pmVsVegas"]["result"] for x in rows if x["result"].get("pmVsVegas")]
    rec = {"weeks": f"Week {weeks[0]}" + (f"–{weeks[-1]}" if len(weeks) > 1 else ""), "games": len(rows),
           "maePM": mean("pmErr"), "maeClaude": mean("claudeErr"), "maeVegas": mean("vegasErr"),
           "pmCloser": cl.count("pm"), "claudeCloser": cl.count("claude"), "ties": cl.count("tie"),
           "pmVsVegas": f"{ats.count('W')}-{ats.count('L')}" + (f"-{ats.count('P')}" if ats.count("P") else "")}
    rec["summary"] = (f"{rec['weeks']}, {rec['games']} games: average miss PM {rec['maePM']:.1f}, Claude {rec['maeClaude']:.1f}, "
                      f"Vegas {rec['maeVegas']:.1f} pts. PM closer than Claude in {rec['pmCloser']}, Claude closer in {rec['claudeCloser']}"
                      + (f", {rec['ties']} ties" if rec["ties"] else "") + f". PM vs the spread (3+ pt gaps): {rec['pmVsVegas']}.")
    return rec


if __name__ == "__main__":
    y, w = int(sys.argv[1]), int(sys.argv[2])
    doc, n = grade_week(y, w, finals(y))
    rec = season_record(y)
    json.dump(rec, open(os.path.join(OUT, f"pm_record_{y}.json"), "w"), indent=1)
    print(f"week {w}: graded {n} of {len(doc['games'])} games")
    print(json.dumps(rec, indent=1))
