"""Research backtest (Oct 2026): which ideas from the literature improve predictions out of sample?
Fit on 2024, test on 2025. Every feature for a game in week W uses only games before W (plus preseason info).

Candidates
  A. Prior (last season's SP+ + returning production + talent), blended with in-season ratings by N/(N+games)
  B. Turnover-luck-adjusted results rating (expected turnovers instead of actual, ~5 pts per turnover)
  C. Efficiency built on success rate (85/15 with explosiveness) vs EPA/play; garbage-time filtered vs not
  D. Situational: rest days, travel distance, time zones crossed, elevation, home-field size
  E. Market: does (model - opening line) predict the line's move to the close? (the CLV test)
Output: model/out/research_2024train_2025test.txt
"""
import os, sys, json, gzip, math
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dataset import load, weekly, closing_spread, closing_total

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = []
def say(*a):
    s = " ".join(str(x) for x in a); print(s); OUT.append(s)
mae = lambda e: float(np.nanmean(np.abs(e)))


def opening_spread(lines, gid):
    ls = lines.get(gid) or []
    for pref in ("consensus", "DraftKings", "ESPN Bet", "Bovada"):
        for l in ls:
            if l.get("provider") == pref and l.get("spreadOpen") is not None:
                return float(l["spreadOpen"])
    for l in ls:
        if l.get("spreadOpen") is not None:
            return float(l["spreadOpen"])
    return np.nan


def hav(lat1, lon1, lat2, lon2):
    if None in (lat1, lon1, lat2, lon2): return np.nan
    p = math.pi / 180
    a = math.sin((lat2 - lat1) * p / 2) ** 2 + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(a))


TZ = {"America/New_York": -5, "America/Detroit": -5, "America/Indiana/Indianapolis": -5, "America/Kentucky/Louisville": -5,
      "America/Chicago": -6, "America/Denver": -7, "America/Boise": -7, "America/Phoenix": -7, "America/Los_Angeles": -8,
      "Pacific/Honolulu": -10, "America/Indiana/Knox": -6}


def games_table(year):
    games = load(year, "games")
    teams = load(2026, "teams_fbs")  # home stadium locations (stable across years for FBS)
    loc = {t["school"]: t.get("location") or {} for t in teams}
    venues = {v["id"]: v for v in (load(2026, "venues") or [])}
    lines = {l["id"]: l["lines"] for l in (load(year, "lines") or [])}
    fbs = {t for g in games for t, c in ((g["homeTeam"], g.get("homeClassification")), (g["awayTeam"], g.get("awayClassification"))) if c == "fbs"}
    rows = []
    for g in games:
        if not g.get("completed") or g.get("homePoints") is None: continue
        v = venues.get(g.get("venueId")) or {}
        hl, al = loc.get(g["homeTeam"], {}), loc.get(g["awayTeam"], {})
        vlat, vlon = v.get("latitude"), v.get("longitude")
        if vlat is None: vlat, vlon = (hl.get("latitude"), hl.get("longitude")) if not g.get("neutralSite") else (None, None)
        velev = v.get("elevation") or (hl.get("elevation") if not g.get("neutralSite") else None)
        vtz = v.get("timezone") or (hl.get("timezone") if not g.get("neutralSite") else None)
        f = lambda x: float(x) if x not in (None, "") else np.nan
        rows.append({"gameId": g["id"], "week": g["week"], "date": g["startDate"][:10], "home": g["homeTeam"], "away": g["awayTeam"],
                     "neutral": bool(g.get("neutralSite")), "hp": g["homePoints"], "ap": g["awayPoints"],
                     "fbs_both": g["homeTeam"] in fbs and g["awayTeam"] in fbs,
                     "spread": closing_spread(lines, g["id"]), "open": opening_spread(lines, g["id"]), "ou": closing_total(lines, g["id"]),
                     "dist_away": hav(al.get("latitude"), al.get("longitude"), vlat, vlon),
                     "dist_home": hav(hl.get("latitude"), hl.get("longitude"), vlat, vlon) if g.get("neutralSite") else 0.0,
                     "tz_away": (TZ.get(vtz, np.nan) - TZ.get(al.get("timezone"), np.nan)) if vtz else np.nan,
                     "tz_home": (TZ.get(vtz, np.nan) - TZ.get(hl.get("timezone"), np.nan)) if vtz else np.nan,
                     "elev_venue": f(velev), "elev_away_home": f(al.get("elevation")), "elev_home_home": f(hl.get("elevation"))})
    G = pd.DataFrame(rows)
    G["margin"] = G.hp - G.ap; G["total"] = G.hp + G.ap
    G["mkt"] = -G.spread; G["mkt_open"] = -G.open
    # rest days: days since each team's previous game (any opponent, incl. FCS)
    G["d"] = pd.to_datetime(G.date)
    last = {}; rh, ra = [], []
    for _, r in G.sort_values("d").iterrows():
        for t, store in ((r.home, rh), (r.away, ra)):
            store.append((r.gameId, (r.d - last[t]).days if t in last else np.nan)); last[t] = r.d
    G["rest_home"] = G.gameId.map(dict(rh)); G["rest_away"] = G.gameId.map(dict(ra))
    return G, fbs


def team_box(year):
    """Per (gameId, team): own fumbles, fumbles lost, giveaways, passes broken up (made), return/defensive TDs."""
    out = {}
    for g in weekly(year, "team_box"):
        for t in g.get("teams") or []:
            st = {x["category"]: x["stat"] for x in t.get("stats", [])}
            def num(k):  # CFBD omits a category when it is zero
                try: return float(st.get(k, 0))
                except: return np.nan
            to, fl = num("turnovers"), num("fumblesLost")
            out[(g["id"], t["team"])] = {"fum": num("totalFumbles"), "fumLost": fl, "intThrown": (to - fl) if to == to and fl == fl else np.nan,
                                         "pbu": num("passesDeflected"), "giveaways": to,
                                         "ntd": sum(v for v in (num("kickReturnTDs"), num("puntReturnTDs"), num("defensiveTDs")) if v == v)}
    return out


def adv_games(year, gt):
    rows = []
    for a in weekly(year, "game_advanced_gt" if gt else "game_advanced"):
        o, d = a["offense"], a["defense"]
        rows.append({"gameId": a["gameId"], "week": a["week"], "team": a["team"], "opp": a["opponent"],
                     "o_epa": o.get("ppa"), "o_sr": o.get("successRate"), "o_xpl": o.get("explosiveness"), "o_plays": o.get("plays")})
    return pd.DataFrame(rows)


def ridge_od(tg, col, teams, lam):
    d = tg[["team", "opp", col]].dropna()
    idx = {t: i for i, t in enumerate(teams)}; d = d[d.team.isin(idx) & d.opp.isin(idx)]
    if len(d) < 20: return None
    n = len(teams); X = np.zeros((len(d), 2 * n)); y = d[col].to_numpy(float); mu = y.mean()
    for r, (t, o) in enumerate(zip(d.team, d.opp)): X[r, idx[t]] = 1; X[r, n + idx[o]] = 1
    beta = np.linalg.solve(X.T @ X + lam * np.eye(2 * n), X.T @ (y - mu))
    return {t: beta[idx[t]] for t in teams}, {t: beta[n + idx[t]] for t in teams}


def ridge_pts(G, teams, col="margin", lam=2.0):
    idx = {t: i for i, t in enumerate(teams)}; n = len(teams)
    g = G[G.home.isin(idx) & G.away.isin(idx)]
    if len(g) < 30: return None
    X = np.zeros((len(g), n + 1)); y = np.clip(g[col].to_numpy(float), -35, 35)
    for r, (h, a, neu) in enumerate(zip(g.home, g.away, g.neutral)): X[r, idx[h]] = 1; X[r, idx[a]] = -1; X[r, n] = 0 if neu else 1
    A = X.T @ X + lam * np.eye(n + 1); A[n, n] -= lam - 1e-6
    beta = np.linalg.solve(A, X.T @ y)
    return {t: beta[idx[t]] for t in teams}, beta[n]


def priors(year):
    """Preseason prior in points: last season's final SP+ (regressed) + returning production + talent."""
    sp = {r["team"]: r.get("rating") for r in (load(year - 1, "sp_ratings") or []) if r.get("rating") is not None}
    ret = {r["team"]: r for r in (load(year, "returning") or [])}
    tal = {r.get("team") or r.get("school"): float(r["talent"]) for r in (load(year, "talent") or []) if r.get("talent") not in (None, "")}
    tv = np.array(list(tal.values())) if tal else np.array([0.0])
    return sp, ret, tal, float(tv.mean()), float(tv.std() or 1)


def build(year, lam_eff=4.0):
    G, fbs = games_table(year)
    teams = sorted(fbs)
    box = team_box(year)
    # turnover luck: actual turnover margin minus expected (own fumbles lost 50%; INTs = 22% of passes defensed)
    def give(gid, t, o):
        bt, bo = box.get((gid, t)), box.get((gid, o))
        if not bt or not bo or any(np.isnan(x) for x in (bt["fum"], bt["fumLost"], bt["intThrown"], bo["pbu"])): return None
        return bt["giveaways"], 0.5 * bt["fum"] + 0.22 * (bt["intThrown"] + bo["pbu"]), bt["ntd"]
    lk, nt = [], []
    for _, r in G.iterrows():
        h, a = give(r.gameId, r.home, r.away), give(r.gameId, r.away, r.home)
        if h and a:
            lk.append((a[0] - h[0]) - (a[1] - h[1])); nt.append(h[2] - a[2])
        else:
            lk.append(np.nan); nt.append(np.nan)
    G["to_luck"] = lk; G["ntd_diff"] = nt
    G["margin_lucky"] = G.margin - 5.0 * G.to_luck.fillna(0)
    G["margin_lucky2"] = G.margin_lucky - 4.0 * G.ntd_diff.fillna(0)
    G["margin_lucky_half"] = G.margin - 2.5 * G.to_luck.fillna(0)   # also discount non-offensive TDs (part already counted via turnovers)
    E = {gt: adv_games(year, gt) for gt in (False, True)}
    sp, ret, tal, tmu, tsd = priors(year)
    rows = []
    for W in sorted(G.week.unique()):
        if W < 2: continue
        gb = G[(G.week < W) & G.fbs_both]
        gp = pd.concat([gb.home, gb.away]).value_counts()
        pr = ridge_pts(gb, teams); prl = ridge_pts(gb, teams, "margin_lucky"); prl2 = ridge_pts(gb, teams, "margin_lucky2"); prlh = ridge_pts(gb, teams, "margin_lucky_half")
        eff = {}
        for gt, tg in E.items():
            tgb = tg[tg.week < W]
            for m in ("o_epa", "o_sr", "o_xpl"):
                eff[(gt, m)] = ridge_od(tgb, m, teams, lam_eff)
        tgb = E[True][E[True].week < W]
        pace = tgb.groupby("team").o_plays.mean(); pace_against = tgb.groupby("opp").o_plays.mean()
        for _, g in G[(G.week == W) & G.fbs_both].iterrows():
            r = g.to_dict()
            r["pace"] = np.nanmean([pace.get(g.home, np.nan), pace.get(g.away, np.nan), pace_against.get(g.home, np.nan), pace_against.get(g.away, np.nan)])
            r["gp_H"], r["gp_A"] = gp.get(g.home, 0), gp.get(g.away, 0)
            if pr: r["rat"] = pr[0].get(g.home, 0) - pr[0].get(g.away, 0); r["hfa_fit"] = pr[1]
            if prl: r["rat_luck"] = prl[0].get(g.home, 0) - prl[0].get(g.away, 0)
            if prl2: r["rat_luck2"] = prl2[0].get(g.home, 0) - prl2[0].get(g.away, 0)
            if prlh: r["rat_luck_half"] = prlh[0].get(g.home, 0) - prlh[0].get(g.away, 0)
            for (gt, m), f in eff.items():
                if not f: continue
                off, dfn = f; k = f"{m}{'_gt' if gt else ''}"
                r[k] = (off.get(g.home, 0) - dfn.get(g.home, 0)) - (off.get(g.away, 0) - dfn.get(g.away, 0))  # (off - def allowed) diff
                r[k + "_tot"] = (off.get(g.home, 0) + dfn.get(g.away, 0)) + (off.get(g.away, 0) + dfn.get(g.home, 0))  # scoring environment
            for s, t in (("H", g.home), ("A", g.away)):
                rp = ret.get(t) or {}
                r[f"sp_prev_{s}"] = sp.get(t, np.nan)
                r[f"ret_ppa_{s}"] = rp.get("percentPPA", np.nan)
                r[f"ret_pass_{s}"] = rp.get("percentPassingPPA", np.nan)
                r[f"ret_usage_{s}"] = rp.get("usage", np.nan)
                r[f"tal_{s}"] = (tal.get(t, np.nan) - tmu) / tsd
            rows.append(r)
    return pd.DataFrame(rows)


if __name__ == "__main__":
    for y in (2024, 2025):
        df = build(y)
        df.to_csv(os.path.join(ROOT, "model", "out", f"research_{y}.csv"), index=False)
        print(y, len(df), "games")
