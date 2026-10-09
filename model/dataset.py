"""Build an as-of-week backtest dataset from the CFBD raw pulls.

For every FBS-vs-FBS regular-season game in week W (W >= MIN_WEEK), team features are computed ONLY from
games in weeks < W of the same season (no look-ahead). Outputs model/out/games_<year>.csv.
"""
import gzip, json, os, glob, math
import numpy as np, pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIN_WEEK = 4
LAM = 4.0  # ridge shrinkage, in "games" units


def load(year, name):
    p = os.path.join(ROOT, "data", str(year), "raw", name + ".json.gz")
    return json.loads(gzip.open(p).read()) if os.path.exists(p) else None


def weekly(year, prefix):
    out = []
    for p in sorted(glob.glob(os.path.join(ROOT, "data", str(year), "raw", prefix + "_w*.json.gz"))):
        out += json.loads(gzip.open(p).read())
    return out


def sdiv(a, b):
    return a / b if b else np.nan


def team_games(year):
    """One row per team per game with offense/defense advanced stats, havoc, sacks and QB info."""
    adv = weekly(year, "game_advanced")
    hav = {(h["gameId"], h["team"]): h for h in (load(year, "game_havoc") or [])}
    box = weekly(year, "game_player_stats")
    qbp = weekly(year, "qb_ppa_games")
    qbppa = {}
    for q in qbp:
        qbppa[(q["week"], q["team"], q["id"])] = (q.get("averagePPA") or {}).get("pass")
    bx = {}  # (gameId, team) -> dict
    for g in box:
        for t in g["teams"]:
            d = {"sacks": 0.0, "tfl": 0.0, "att": 0.0, "qbs": [], "tfl_players": []}
            for c in t["categories"]:
                for ty in c["types"]:
                    for a in ty["athletes"]:
                        v = a.get("stat")
                        if c["name"] == "defensive" and ty["name"] in ("SACKS", "TFL"):
                            try: x = float(v)
                            except: x = 0.0
                            d["sacks" if ty["name"] == "SACKS" else "tfl"] += x
                            if ty["name"] == "TFL" and x > 0: d["tfl_players"].append((a["id"], a["name"], x))
                        if c["name"] == "passing" and ty["name"] == "C/ATT":
                            try: att = float(str(v).split("/")[1])
                            except: att = 0.0
                            d["att"] += att; d["qbs"].append((a["id"], a["name"], att))
            bx[(g["id"], t["team"])] = d
    rows = []
    for a in adv:
        o, df = a["offense"], a["defense"]
        def plays(side, k):
            s = side.get(k) or {}
            return sdiv(s.get("totalPPA") or 0, s.get("ppa")) if s.get("ppa") else np.nan
        nr, npass = plays(o, "rushingPlays"), plays(o, "passingPlays")
        h = hav.get((a["gameId"], a["team"]), {})
        b, bo = bx.get((a["gameId"], a["team"]), {}), bx.get((a["gameId"], a["opponent"]), {})
        qbs = sorted(b.get("qbs", []), key=lambda x: -x[2])
        qb = qbs[0] if qbs else None
        rows.append({
            "gameId": a["gameId"], "week": a["week"], "team": a["team"], "opp": a["opponent"],
            "o_epa": o.get("ppa"), "d_epa": df.get("ppa"),
            "o_rush_epa": (o.get("rushingPlays") or {}).get("ppa"), "d_rush_epa": (df.get("rushingPlays") or {}).get("ppa"),
            "o_pass_epa": (o.get("passingPlays") or {}).get("ppa"), "d_pass_epa": (df.get("passingPlays") or {}).get("ppa"),
            "o_stuff": o.get("stuffRate"), "d_stuff": df.get("stuffRate"),
            "o_line": o.get("lineYards"), "d_line": df.get("lineYards"),
            "rush_rate": sdiv(nr, (nr or 0) + (npass or 0)) if nr == nr and npass == npass else np.nan,
            "plays": o.get("plays"),
            "o_f7havoc": (h.get("offense") or {}).get("frontSevenHavocRate"), "d_f7havoc": (h.get("defense") or {}).get("frontSevenHavocRate"),
            "o_dbhavoc": (h.get("offense") or {}).get("dbHavocRate"), "d_dbhavoc": (h.get("defense") or {}).get("dbHavocRate"),
            "d_sack_rate": sdiv(b.get("sacks", 0), bo.get("att", 0) + b.get("sacks", 0)) if bo else np.nan,
            "o_sack_rate": sdiv(bo.get("sacks", 0), b.get("att", 0) + bo.get("sacks", 0)) if bo else np.nan,
            "qb_id": qb[0] if qb else None, "qb_name": qb[1] if qb else None, "qb_att": qb[2] if qb else 0,
            "qb_pass_epa": qbppa.get((a["week"], a["team"], qb[0])) if qb else None,
        })
    return pd.DataFrame(rows)


def ridge_offdef(tg, col_o, col_d, teams):
    """value(T offense vs O defense) = mu + off[T] + def[O]; uses both the offense row (col_o) and the
    mirrored defense row is the opponent's offense row, so we fit on offense observations only."""
    d = tg[["team", "opp", col_o]].dropna()
    if len(d) < 20:
        return None
    idx = {t: i for i, t in enumerate(teams)}
    d = d[d.team.isin(idx) & d.opp.isin(idx)]
    n = len(teams)
    X = np.zeros((len(d), 2 * n)); y = d[col_o].to_numpy(float)
    mu = y.mean()
    for r, (t, o) in enumerate(zip(d.team, d.opp)):
        X[r, idx[t]] = 1; X[r, n + idx[o]] = 1
    A = X.T @ X + LAM * np.eye(2 * n); b = X.T @ (y - mu)
    beta = np.linalg.solve(A, b)
    return mu, {t: beta[idx[t]] for t in teams}, {t: beta[n + idx[t]] for t in teams}


def points_ratings(games_before, teams):
    """Ridge margin ratings to date (like Claude's results model): margin = hfa*home + r[H] - r[A]."""
    idx = {t: i for i, t in enumerate(teams)}; n = len(teams)
    g = games_before[games_before.home.isin(idx) & games_before.away.isin(idx)]
    if len(g) < 30: return None
    X = np.zeros((len(g), n + 1)); y = np.clip(g.margin.to_numpy(float), -35, 35)
    for r, (h, a, neu) in enumerate(zip(g.home, g.away, g.neutral)):
        X[r, idx[h]] = 1; X[r, idx[a]] = -1; X[r, n] = 0 if neu else 1
    A = X.T @ X + 2.0 * np.eye(n + 1); A[n, n] -= 2.0 - 1e-6
    beta = np.linalg.solve(A, X.T @ y)
    return {t: beta[idx[t]] for t in teams}, beta[n]


def closing_spread(lines_by_game, gid):
    ls = lines_by_game.get(gid) or []
    for pref in ("consensus", "DraftKings", "ESPN Bet", "Bovada", "William Hill (New Jersey)"):
        for l in ls:
            if l.get("provider") == pref and l.get("spread") is not None:
                return float(l["spread"])
    for l in ls:
        if l.get("spread") is not None:
            return float(l["spread"])
    return np.nan


def build(year):
    games = load(year, "games")
    fbs = {t for g in games for t, c in ((g["homeTeam"], g.get("homeClassification")), (g["awayTeam"], g.get("awayClassification"))) if c == "fbs"}
    G = pd.DataFrame([{"gameId": g["id"], "week": g["week"], "home": g["homeTeam"], "away": g["awayTeam"], "neutral": bool(g.get("neutralSite")),
                       "hp": g.get("homePoints"), "ap": g.get("awayPoints")} for g in games if g.get("completed") and g.get("homePoints") is not None])
    G["margin"] = G.hp - G.ap
    lines = {l["id"]: l["lines"] for l in (load(year, "lines") or [])}
    G["spread"] = [closing_spread(lines, gid) for gid in G.gameId]
    TG = team_games(year)
    teams = sorted(fbs)
    out = []
    metrics = [("o_epa",), ("o_rush_epa",), ("o_pass_epa",), ("o_stuff",), ("o_f7havoc",), ("o_sack_rate",), ("o_dbhavoc",)]
    for W in sorted(G.week.unique()):
        if W < MIN_WEEK: continue
        tgb = TG[TG.week < W]
        gb = G[G.week < W]
        fits = {m[0]: ridge_offdef(tgb, m[0], None, teams) for m in metrics}
        pr = points_ratings(gb, teams)
        rr = tgb.groupby("team").rush_rate.mean(); lg_rr = tgb.rush_rate.mean()
        # QB: season-to-date primary QB pass EPA per game, and the most recent starter's EPA
        qb_hist = tgb.dropna(subset=["qb_pass_epa"]).sort_values("week")
        for _, g in G[(G.week == W) & G.home.isin(fbs) & G.away.isin(fbs)].iterrows():
            r = {"year": year, "week": W, "gameId": g.gameId, "home": g.home, "away": g.away, "neutral": g.neutral, "margin": g.margin,
                 "spread": g.spread, "mkt": -g.spread if g.spread == g.spread else np.nan}
            if pr:
                rat, hfa = pr; r["rat"] = rat.get(g.home, 0) - rat.get(g.away, 0) + (0 if g.neutral else hfa)
            for m, f in fits.items():
                if not f: continue
                mu, off, dfn = f
                # expected offense value for home offense vs away defense, and away offense vs home defense
                r[f"{m}_H"] = mu + off.get(g.home, 0) + dfn.get(g.away, 0)
                r[f"{m}_A"] = mu + off.get(g.away, 0) + dfn.get(g.home, 0)
                r[f"{m}_offH"], r[f"{m}_defA"] = off.get(g.home, 0), dfn.get(g.away, 0)
                r[f"{m}_offA"], r[f"{m}_defH"] = off.get(g.away, 0), dfn.get(g.home, 0)
            r["rr_H"], r["rr_A"], r["rr_lg"] = rr.get(g.home, np.nan), rr.get(g.away, np.nan), lg_rr
            for side, t in (("H", g.home), ("A", g.away)):
                q = qb_hist[qb_hist.team == t]
                if len(q):
                    w_att = q.qb_att.clip(lower=1)
                    r[f"qb_season_{side}"] = float(np.average(q.qb_pass_epa, weights=w_att))
                    last = q.iloc[-1]
                    same = q[q.qb_id == last.qb_id]
                    r[f"qb_last_{side}"] = float(np.average(same.qb_pass_epa, weights=same.qb_att.clip(lower=1)))
                    r[f"qb_change_{side}"] = int(len(q) >= 2 and q.iloc[-1].qb_id != q.iloc[-2].qb_id)
                    r[f"att_pg_{side}"] = float(q.qb_att.mean())
            out.append(r)
    df = pd.DataFrame(out)
    os.makedirs(os.path.join(ROOT, "model", "out"), exist_ok=True)
    df.to_csv(os.path.join(ROOT, "model", "out", f"games_{year}.csv"), index=False)
    TG.to_csv(os.path.join(ROOT, "model", "out", f"teamgames_{year}.csv.gz"), index=False)
    return df


if __name__ == "__main__":
    import sys
    for y in (sys.argv[1:] or ["2024", "2025"]):
        d = build(int(y)); print(y, len(d), "games;", d.mkt.notna().sum(), "with lines")
