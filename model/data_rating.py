"""Data Rating (Player Model v2 component): the best purely data-driven team rating from the Oct 2026 research backtest.

rating = prior x N/(N+g) + this season x g/(N+g),  N = 2 games, g = games played
  prior        = 0.87 x last season's final SP+ + 4.88 x roster talent (z-score)        [coefficients refit on 2024+2025]
  this season  = 1.25 x results rating (ridge, margins capped at 35, turnover luck half-removed: 2.5 pts per turnover
                 above/below expectation, where expected = half of own fumbles lost + 22% of passes defensed intercepted)
               + 10.2 x opponent-adjusted success rate (offense minus defense allowed, garbage time removed)
Backtest (fit 2024, test 2025, FBS weeks 2+): average miss 12.14 pts vs 13.32 for in-season results alone and 11.83 for the closing line.
"""
import os, sys, json
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from research import games_table, team_box, adv_games, ridge_od, ridge_pts, priors

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def team_ratings(year, week):
    C = json.load(open(os.path.join(ROOT, "model", "out", "rr_coefs.json")))
    c, N, k = C["coef"], C["N"], C["lucky_pts_per_turnover"]
    G, fbs = games_table(year)
    teams = sorted(fbs)
    box = team_box(year)
    def give(gid, t, o):
        bt, bo = box.get((gid, t)), box.get((gid, o))
        if not bt or not bo or any(np.isnan(x) for x in (bt["fum"], bt["intThrown"], bo["pbu"], bt["giveaways"])): return None
        return bt["giveaways"], 0.5 * bt["fum"] + 0.22 * (bt["intThrown"] + bo["pbu"])
    luck = []
    for _, r in G.iterrows():
        h, a = give(r.gameId, r.home, r.away), give(r.gameId, r.away, r.home)
        luck.append(((a[0] - h[0]) - (a[1] - h[1])) if h and a else 0.0)
    G["luck"] = luck; G["margin_lucky_half"] = G.margin - k * G.luck
    gb = G[(G.week < week) & G.fbs_both]
    lk = gb.groupby("home").luck.sum().sub(gb.groupby("away").luck.sum(), fill_value=0)
    gp = pd.concat([gb.home, gb.away]).value_counts()
    rp = ridge_pts(gb, teams, "margin_lucky_half"); rat = rp[0] if rp else {}      # too few games (weeks 1-2): prior only
    tg = adv_games(year, True); tg = tg[tg.week < week] if len(tg) else tg
    od = ridge_od(tg, "o_sr", teams, 4.0) if len(tg) else None; off, dfn = od if od else ({}, {})
    sp, ret, tal, tmu, tsd = priors(year)
    sp_fill = float(np.nanpercentile([v for t, v in sp.items() if t in fbs], 25))  # teams new to FBS: below-average prior
    out = {}
    for t in teams:
        g = gp.get(t, 0) if rp else 0; wi = g / (N + g); wp = 1 - wi
        prior = c["p_sp"] * sp.get(t, sp_fill) + c["p_tal"] * (((tal.get(t, tmu - tsd)) - tmu) / tsd)
        season = c["rat_luck_half"] * rat.get(t, 0) + c["o_sr_gt"] * (off.get(t, 0) - dfn.get(t, 0))
        out[t] = {"rating": wp * prior + wi * season, "prior": prior, "season": season, "games": int(g), "priorWeight": round(wp, 3),
                  "luck": float(lk.get(t, 0.0))}
    return out, {"hfa": c["hfa"], "const": c["const"], "N": N}


if __name__ == "__main__":
    y, w = int(sys.argv[1]), int(sys.argv[2])
    R, meta = team_ratings(y, w)
    top = sorted(R.items(), key=lambda kv: -kv[1]["rating"])[:25]
    for i, (t, v) in enumerate(top, 1):
        print(f"{i:2d} {t:22s} {v['rating']:6.1f}  prior {v['prior']:6.1f} (weight {v['priorWeight']:.2f})  season {v['season']:6.1f}  TO luck {v['luck']:+.1f}")
