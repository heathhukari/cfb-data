"""Transitive Letdown Theory (TLT) test.

The theory (Heath, Oct 2026): a team that "owns" an opponent gets owned itself the next week, and it chains:
Ole Miss beat LSU -> Ole Miss got owned at Florida -> Florida got owned at Missouri -> Missouri vs Texas A&M = ?

Definitions (FBS vs FBS regular-season games, 2014-2026 except 2020):
  owned      = won by 17+ points
  link       = team X owned team Y in its last game, AND Y had won its own previous game (Y was "coming off" a win)
  strong link= same, but Y had OWNED someone in its previous game (the exact Florida -> Missouri pattern)
For X's NEXT game we compare what happened with what the closing line expected:
  - ATS: did X cover?            - straight up: did X lose (vs market-implied loss chance)?
  - got owned: did X lose by 17+ (vs the chance implied by the line, normal with SD 14.8)?
Output: model/out/tlt_study.txt and model/out/tlt_study.json
"""
import os, sys, json, gzip, math
import numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dataset import closing_spread

SD, OWN = 14.8, 17
phi = lambda z: 0.5 * (1 + math.erf(z / math.sqrt(2)))


def load(y, n):
    p = os.path.join(ROOT, "data", str(y), "raw", n + ".json.gz")
    return json.loads(gzip.open(p).read()) if os.path.exists(p) else None


rows = []
for y in [y for y in range(2014, 2027) if y != 2020]:
    G, L = load(y, "games"), load(y, "lines")
    if not G: continue
    lines = {l["id"]: l["lines"] for l in (L or [])}
    for g in G:
        if g.get("seasonType") != "regular" or not g.get("completed") or g.get("homePoints") is None: continue
        if g.get("homeClassification") != "fbs" or g.get("awayClassification") != "fbs": continue
        sp = closing_spread(lines, g["id"])
        for side in ("home", "away"):
            o = "away" if side == "home" else "home"
            m = (g["homePoints"] - g["awayPoints"]) * (1 if side == "home" else -1)
            exp = (-sp if side == "home" else sp) if sp == sp else np.nan   # market's expected margin for this team
            rows.append({"year": y, "week": g["week"], "date": g["startDate"], "gameId": g["id"], "team": g[side + "Team"], "opp": g[o + "Team"],
                         "margin": m, "exp": exp, "score": f'{g[side + "Points"]}-{g[o + "Points"]}'})
T = pd.DataFrame(rows).sort_values(["team", "date"]).reset_index(drop=True)
T["prev_margin"] = T.groupby(["team", "year"]).margin.shift(1)          # this team's previous FBS game
T["next_margin"] = T.groupby(["team", "year"]).margin.shift(-1)
T["next_exp"] = T.groupby(["team", "year"]).exp.shift(-1)
T["next_opp"] = T.groupby(["team", "year"]).opp.shift(-1)
T["next_week"] = T.groupby(["team", "year"]).week.shift(-1)
# the opponent's previous game result (was the victim coming off a win / an owning?)
opp_prev = T.set_index(["gameId", "team"]).prev_margin
T["opp_prev_margin"] = [opp_prev.get((g, o), np.nan) for g, o in zip(T.gameId, T.opp)]
# full chain: the victim Y had owned Z in its previous game, and Z had won ITS game before that (Ole Miss beat LSU -> Florida owned Ole Miss -> Missouri owned Florida)
prev_opp = T.groupby(["team", "year"]).opp.shift(1); T["prev_opp"] = prev_opp; T["prev_gameId"] = T.groupby(["team", "year"]).gameId.shift(1)
key = T.set_index(["gameId", "team"])
T["opp_prev_opp"] = [key.prev_opp.get((g, o), None) for g, o in zip(T.gameId, T.opp)]
T["opp_prev_gid"] = [key.prev_gameId.get((g, o), None) for g, o in zip(T.gameId, T.opp)]
T["z_prev_margin"] = [key.prev_margin.get((pg, z), np.nan) if z is not None and pg == pg and pg is not None else np.nan for pg, z in zip(T.opp_prev_gid, T.opp_prev_opp)]
T = T[T.next_margin.notna() & T.next_exp.notna() & (T.next_week - T.week <= 2)]   # next game within two weeks, with a line

def summarize(d, label):
    n = len(d)
    if n == 0: return {"label": label, "n": 0}
    cover = (d.next_margin - d.next_exp)
    ats = f"{int((cover > 0).sum())}-{int((cover < 0).sum())}-{int((cover == 0).sum())}"
    lost = int((d.next_margin < 0).sum()); exp_lost = float(sum(phi(-e / SD) for e in d.next_exp))
    owned = int((d.next_margin <= -OWN).sum()); exp_owned = float(sum(phi((-OWN - e) / SD) for e in d.next_exp))
    se = cover.std(ddof=1) / math.sqrt(n) if n > 1 else float("nan")
    return {"label": label, "n": n, "ats": ats, "coverPct": round(100 * (cover > 0).sum() / max(1, (cover != 0).sum()), 1),
            "vsLine": round(float(cover.mean()), 2), "vsLineSE": round(float(se), 2),
            "lost": lost, "expLost": round(exp_lost, 1), "gotOwned": owned, "expGotOwned": round(exp_owned, 1)}

groups = [
    ("Every team, next game (baseline)", T),
    ("Won its last game", T[T.margin > 0]),
    ("OWNED its last opponent (won by 17+)", T[T.margin >= OWN]),
    ("Owned an opponent that had WON its previous game (TLT link)", T[(T.margin >= OWN) & (T.opp_prev_margin > 0)]),
    ("Owned an opponent that had OWNED someone its previous game (strong TLT link: the Florida -> Missouri spot)", T[(T.margin >= OWN) & (T.opp_prev_margin >= OWN)]),
    ("FULL CHAIN: owned a team that had owned a team that had just won (Ole Miss -> Florida -> Missouri pattern)", T[(T.margin >= OWN) & (T.opp_prev_margin >= OWN) & (T.z_prev_margin > 0)]),
    ("Beat the line by 14+ in its last game", T[(T.margin - T.exp) >= 14]),
]
res = [summarize(d, l) for l, d in groups]
out = ["Transitive Letdown Theory test: FBS vs FBS regular season, 2014-2026 (no 2020). 'Owned' = won by 17+.",
       "For the team's NEXT game, compared with what the closing line expected (SD 14.8 for win/blowout chances).", ""]
for r in res:
    if not r["n"]: out.append(f"{r['label']}: no games"); continue
    out.append(f"{r['label']}\n   n={r['n']}  ATS {r['ats']} ({r['coverPct']}%)  avg vs line {r['vsLine']:+.2f} (± {r['vsLineSE']:.2f})  "
               f"lost {r['lost']} (line expected {r['expLost']})  got owned {r['gotOwned']} (line expected {r['expGotOwned']})")
# the 2026 chain itself
chain = T[(T.year == 2026)]
out.append("\n2026 chain so far:")
for t, w in (("Ole Miss", 3), ("Florida", 4), ("Missouri", 5)):
    r = T[(T.year == 2026) & (T.team == t) & (T.week == w)]
    for _, x in r.iterrows():
        out.append(f"   wk {w}: {t} {x.score} vs {x.opp} -> next: vs {x.next_opp}, margin {x.next_margin:+.0f} (line expected {x.next_exp:+.1f})")
open(os.path.join(ROOT, "model", "out", "tlt_study.txt"), "w").write("\n".join(out) + "\n")
json.dump(res, open(os.path.join(ROOT, "model", "out", "tlt_study.json"), "w"), indent=1)
print("\n".join(out))
