"""Player-impact model ("PM") for the current week.

PM Power = 0.6 x Claude Power + 0.4 x Unit Power + QB adjustment + injury adjustments.
 - Unit Power: opponent-adjusted EPA per play (offense minus defense) x 70 plays, centred on Claude Power's FBS mean.
   Backtest (fit 2024, test 2025): a results-only rating missed by 12.81 pts/game; adding this efficiency rating cut it to 12.75.
 - QB adjustment: only when the starter changes; 0.5 x (current starter's pass EPA/dropback - team season QB EPA/dropback) x dropbacks/game.
   Halved on purpose: in QB-change games the closing line over-reacted to the new QB's form in 2024 and 2025.
 - Injury adjustments (input injuries.json): starting QB out -> backup (or replacement level) instead; skill player out -> -0.5 x his
   EPA added per game (cap 3); top havoc defender out -> up to -1.5 by his share of team TFL+sacks. Rough by design.
 - Matchup interactions (run game vs defensive front, protection vs pass rush, ...) are shown as notes with ZERO weight:
   none predicted margins or totals out of sample (see model/out/*.txt).
Usage: python model/player_model.py <year> <week> [injuries.json]  -> model/out/playermodel_<year>_w<week>.json
"""
import json, os, sys, gzip
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dataset import team_games, ridge_offdef, load

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W_CLAUDE, W_UNIT, QB_SHRINK = 0.6, 0.4, 0.5
HFA, SD, FCS = 2.5, 14.8, -24.0  # same constants as Claude's game projections
r1 = lambda x: None if x is None or x != x else round(float(x), 1)
r2 = lambda x: None if x is None or x != x else round(float(x), 2)
r3 = lambda x: None if x is None or x != x else round(float(x), 3)


def rank_of(d, reverse=True):
    s = sorted([(v, k) for k, v in d.items() if v == v], reverse=reverse)
    return {k: i + 1 for i, (v, k) in enumerate(s)}


def main(year, week, inj_path=None):
    names = json.load(open(os.path.join(ROOT, "data", "meta", "names.json")))  # cfbd/espn id -> dashboard name
    teams_raw = load(year, "teams_fbs")
    cf2dash = {t["school"]: names.get(str(t["id"]), t["school"]) for t in teams_raw}
    fbs = set(cf2dash)
    claude = json.load(open(os.path.join(ROOT, "data", str(year), f"claude_w{week:02d}.json")))
    CP = claude["power"]; T25 = claude["teams"]
    inj = json.load(open(inj_path)) if inj_path and os.path.exists(inj_path) else {"source": None, "teams": {}}

    TG = team_games(year)
    TG = TG[TG.week < week]
    tl = sorted(fbs)
    fits = {m: ridge_offdef(TG, m, None, tl) for m in ["o_epa", "o_rush_epa", "o_pass_epa", "o_f7havoc", "o_stuff", "o_sack_rate", "o_dbhavoc"]}
    off, dfn = fits["o_epa"][1], fits["o_epa"][2]
    # plays per game (own offense) and faced (opponents' offense vs this team)
    TG["rush_plays"] = TG.rush_rate * TG.plays; TG["pass_plays"] = (1 - TG.rush_rate) * TG.plays
    own = TG.groupby("team")[["rush_plays", "pass_plays", "plays", "rush_rate"]].mean()
    faced = TG.groupby("opp")[["rush_plays", "pass_plays"]].mean()
    up_raw = {t: (off[t] - dfn[t]) * 70 for t in tl}
    cp_mean = np.mean([CP[cf2dash[t]] for t in tl if cf2dash[t] in CP]); up_mean = np.mean(list(up_raw.values()))
    UP = {t: up_raw[t] - up_mean + cp_mean for t in tl}
    units = {}
    for t in tl:
        rp, pp = own.rush_plays.get(t, 35), own.pass_plays.get(t, 33)
        frp, fpp = faced.rush_plays.get(t, 35), faced.pass_plays.get(t, 33)
        units[t] = {"rushO": fits["o_rush_epa"][1][t] * rp, "passO": fits["o_pass_epa"][1][t] * pp,
                    "rushD": -fits["o_rush_epa"][2][t] * frp, "passD": -fits["o_pass_epa"][2][t] * fpp,
                    "runRate": own.rush_rate.get(t, np.nan),
                    "frontHavoc": fits["o_f7havoc"][2][t], "stuffD": fits["o_stuff"][2][t], "sackD": fits["o_sack_rate"][2][t],
                    "sackAllowed": fits["o_sack_rate"][1][t], "dbHavoc": fits["o_dbhavoc"][2][t]}
    RK = {k: rank_of({t: units[t][k] for t in tl}, reverse=(k not in ("sackAllowed",))) for k in units[tl[0]]}
    # ---- players (season to date) ----
    ppa = load(year, "player_ppa_season") or []; usage = {(u["team"], u["id"]): u["usage"] for u in (load(year, "player_usage") or [])}
    stats = load(year, "player_season_stats") or []
    dstat = {}
    for s in stats:
        if s["team"] in fbs and s["category"] in ("defensive", "interceptions"):
            k = (s["team"], s["playerId"]); d = dstat.setdefault(k, {"name": s["player"], "pos": s.get("position"), "TFL": 0, "SACKS": 0, "QB HUR": 0, "PD": 0, "INT": 0})
            if s["statType"] in d:
                try: d[s["statType"]] += float(s["stat"])
                except: pass
    gp = TG.groupby("team").gameId.nunique()
    players = {}
    for t in tl:
        P = [p for p in ppa if p["team"] == t]
        def u(p, k): return (usage.get((t, p["id"])) or {}).get(k) or 0
        qbs = sorted([p for p in P if p["position"] == "QB"], key=lambda p: -u(p, "pass"))
        rbs = sorted([p for p in P if p["position"] == "RB"], key=lambda p: -u(p, "rush"))[:2]
        rec = sorted([p for p in P if p["position"] in ("WR", "TE")], key=lambda p: -((p["totalPPA"] or {}).get("pass") or 0))[:3]
        dfs = sorted([dict(id=k[1], **v) for k, v in dstat.items() if k[0] == t], key=lambda d: -(d["TFL"] + d["SACKS"] + 0.5 * d["QB HUR"]))[:4]
        g = max(1, int(gp.get(t, 1)))
        tot_havoc = sum(d["TFL"] + d["SACKS"] for k, d in dstat.items() if k[0] == t) or 1
        fmt = lambda p, role: {"id": p["id"], "name": p["name"], "pos": p["position"], "role": role,
                               "epaPlay": r3((p["averagePPA"] or {}).get("pass" if role in ("QB", "REC") else "rush" if role == "RB" else "all")),
                               "epaGame": r2(((p["totalPPA"] or {}).get("pass" if role in ("QB", "REC") else "rush" if role == "RB" else "all") or 0) / g),
                               "usage": r3(u(p, "pass" if role in ("QB", "REC") else "rush"))}
        players[t] = {"qb": [fmt(p, "QB") for p in qbs[:2]], "rb": [fmt(p, "RB") for p in rbs], "rec": [fmt(p, "REC") for p in rec],
                      "def": [{"id": d["id"], "name": d["name"], "pos": d["pos"], "tfl": d["TFL"], "sacks": d["SACKS"], "hurries": d["QB HUR"], "pd": d["PD"], "int": d["INT"],
                               "havocShare": r3((d["TFL"] + d["SACKS"]) / tot_havoc)} for d in dfs]}
    # ---- QB adjustment from game logs ----
    qbq = TG.dropna(subset=["qb_pass_epa"]).sort_values("week")
    allqb = qbq.groupby("qb_id").apply(lambda q: np.average(q.qb_pass_epa, weights=q.qb_att.clip(lower=1)) if q.qb_att.sum() >= 40 else np.nan, include_groups=False).dropna()
    repl = float(np.percentile(allqb, 20)) if len(allqb) else -0.05
    qbinfo = {}
    for t in tl:
        q = qbq[qbq.team == t]
        if not len(q): qbinfo[t] = {"adj": 0.0}; continue
        season = float(np.average(q.qb_pass_epa, weights=q.qb_att.clip(lower=1)))
        last = q.iloc[-1]; cur = q[q.qb_id == last.qb_id]
        cur_epa = float(np.average(cur.qb_pass_epa, weights=cur.qb_att.clip(lower=1)))
        att_pg = float(q.qb_att.mean())
        changed = len(q.qb_id.unique()) > 1 and len(cur) < len(q)
        n_cur = int(cur.gameId.nunique())
        # halve (market over-reacts to new-QB form) and discount small samples: 1 start counts 1/3, 2 starts 1/2, 4 starts 2/3
        adj = QB_SHRINK * (cur_epa - season) * att_pg * (n_cur / (n_cur + 2)) if changed else 0.0
        qbinfo[t] = {"starter": last.qb_name, "starterId": str(last.qb_id), "starterEpa": cur_epa, "teamSeasonEpa": season, "attPg": att_pg,
                     "changed": bool(changed), "starterGames": int(cur.gameId.nunique()), "adj": float(np.clip(adj, -6, 6)), "backups": q[q.qb_id != last.qb_id].groupby(["qb_id", "qb_name"]).qb_att.sum().to_dict()}
    # ---- injuries (Covers lists "F. Lastname") ----
    SUF = {"jr.", "jr", "sr.", "ii", "iii", "iv", "v"}
    def key(n):
        t = [x for x in n.lower().replace(",", "").split() if x not in SUF]
        return (t[0][0] if t else "", " ".join(t[1:]) if len(t) > 1 else "")
    def same(cov, full): return key(cov) == key(full) and key(cov)[1] != ""
    injadj = {t: [] for t in tl}
    for dash_name, lst in (inj.get("teams") or {}).items():
        t = next((k for k, v in cf2dash.items() if v == dash_name), None)
        if not t: continue
        pl, qi = players.get(t, {}), qbinfo.get(t, {})
        for x in lst:
            st = str(x.get("st", "")); out = st.lower().startswith("out"); nm = x.get("n", "")
            if qi.get("starter") and same(nm, qi["starter"]):
                if not out:
                    injadj[t].append({"player": nm, "pos": "QB", "status": st, "pts": 0.0, "note": "starting QB listed doubtful — not adjusted"}); continue
                bk = [k for k, a in sorted(qi["backups"].items(), key=lambda kv: -kv[1]) if a >= 30]
                rep_epa, who = repl, "replacement level"
                if bk:
                    bq = qbq[(qbq.team == t) & (qbq.qb_id == bk[0][0])]
                    rep_epa, who = float(np.average(bq.qb_pass_epa, weights=bq.qb_att.clip(lower=1))), bk[0][1]
                a = float(np.clip(0.8 * (rep_epa - qi["starterEpa"]) * qi["attPg"], -10, 0))
                injadj[t].append({"player": nm, "pos": "QB", "status": st, "pts": r1(a), "note": f"starter out; next man up: {who}"}); continue
            if x.get("pos") == "QB":
                injadj[t].append({"player": nm, "pos": "QB", "status": st, "pts": 0.0, "note": "not the current starter — no change"}); continue
            hit = None
            cpos = str(x.get("pos", "")).upper()
            DEFP = {"DL", "DE", "DT", "NT", "EDGE", "LB", "ILB", "OLB", "MLB", "CB", "S", "FS", "SS", "DB"}
            for grp in ("rb", "rec") if cpos not in DEFP else ():
                for p in pl.get(grp, []):
                    if same(nm, p["name"]): hit = ("skill", p)
            for p in (pl.get("def", []) if cpos in DEFP else []):
                if same(nm, p["name"]): hit = ("def", p)
            if not out or not hit: continue
            if hit[0] == "skill":
                injadj[t].append({"player": hit[1]["name"], "pos": hit[1]["pos"], "status": st, "pts": r1(-min(3, 0.5 * max(0, hit[1]["epaGame"] or 0))), "note": "0.5 x EPA added per game"})
            else:
                injadj[t].append({"player": hit[1]["name"], "pos": hit[1]["pos"], "status": st, "pts": r1(-min(1.5, 3 * (hit[1]["havocShare"] or 0))), "note": "share of team TFL + sacks"})
    # ---- PM power ----
    rows = []
    for t in tl:
        dn = cf2dash[t]; cp = CP.get(dn)
        if cp is None: continue
        ia = sum(x["pts"] or 0 for x in injadj[t]); qa = qbinfo[t]["adj"]
        pm = W_CLAUDE * cp + W_UNIT * UP[t] + qa + ia
        rows.append({"team": dn, "pm": pm, "claudePower": cp, "unitPower": UP[t], "qbAdj": qa, "injAdj": ia})
    pmr = rank_of({r["team"]: r["pm"] for r in rows}); cpr = rank_of({r["team"]: r["claudePower"] for r in rows}); upr = rank_of({r["team"]: r["unitPower"] for r in rows})
    # ---- PM Top 25: Claude's Top 25 score with Claude Power swapped for PM power inside the 70% power share ----
    top = []
    for r in rows:
        c = T25.get(r["team"])
        if not c: continue
        top.append({**r, "score": c["score"] + 0.7 * (r["pm"] - r["claudePower"]), "claudeRank": c["rank"], "apRank": c.get("apRank")})
    top.sort(key=lambda x: -x["score"])
    d2c = {v: k for k, v in cf2dash.items()}
    def team_card(dn):
        t = d2c[dn]; u = units[t]; qi = qbinfo[t]
        return {"units": {k: (r2(v) if k in ("rushO", "passO", "rushD", "passD") else r3(v)) for k, v in u.items()},
                "unitRanks": {k: RK[k][t] for k in u},
                "qb": {k: (r3(v) if isinstance(v, float) else v) for k, v in qi.items() if k != "backups"},
                "players": players[t], "injuries": injadj[t]}
    out_top = []
    for i, x in enumerate(top[:25]):
        out_top.append({"rank": i + 1, "team": x["team"], "score": r2(x["score"]), "pm": r1(x["pm"]), "pmRk": pmr[x["team"]], "claudePower": r1(x["claudePower"]), "claudePowerRk": cpr[x["team"]],
                        "unitPower": r1(x["unitPower"]), "unitPowerRk": upr[x["team"]], "qbAdj": r1(x["qbAdj"]), "injAdj": r1(x["injAdj"]), "claudeRank": x["claudeRank"], "apRank": x["apRank"]})
    # ---- this week's games ----
    PMd = {r["team"]: r["pm"] for r in rows}
    focus = set(x["team"] for x in out_top) | {k for k, v in T25.items() if v.get("rank", 99) <= 25 or v.get("apRank")}
    games = []
    for g in claude.get("games", []):
        if g["home"] not in focus and g["away"] not in focus: continue
        if g["home"] not in PMd or g["away"] not in PMd or g.get("claudeHomeMargin") is None: continue
        hfa = 0 if g["neutral"] else 2.5
        pmm = PMd[g["home"]] - PMd[g["away"]] + hfa
        th, ta = d2c[g["home"]], d2c[g["away"]]
        notes = []
        def nt(o, d, od, dd):
            ro, rd = RK, RK
            if ro["runRate"][o] <= 30 and rd["frontHavoc"][d] <= 25: notes.append(f"Run-heavy {od} (#{ro['runRate'][o]} in run rate) vs {dd}'s front seven (#{rd['frontHavoc'][d]} in havoc rate)")
            if ro["runRate"][o] <= 30 and rd["stuffD"][d] <= 20: notes.append(f"{od} leans on the run; {dd} stuffs runs at the line (#{rd['stuffD'][d]})")
            if ro["sackAllowed"][o] >= 100 and rd["sackD"][d] <= 30: notes.append(f"{od}'s protection (#{ro['sackAllowed'][o]} in sack rate allowed) vs {dd}'s pass rush (#{rd['sackD'][d]})")
            if ro["rushO"][o] <= 20 and rd["rushD"][d] <= 20: notes.append(f"Strength on strength: {od} run game #{ro['rushO'][o]} vs {dd} run defense #{rd['rushD'][d]}")
            if ro["passO"][o] <= 20 and rd["passD"][d] <= 20: notes.append(f"Strength on strength: {od} pass game #{ro['passO'][o]} vs {dd} pass defense #{rd['passD'][d]}")
            if ro["passO"][o] <= 25 and rd["passD"][d] >= 100: notes.append(f"Mismatch: {od} pass game #{ro['passO'][o]} vs {dd} pass defense #{rd['passD'][d]}")
            if ro["rushO"][o] <= 25 and rd["rushD"][d] >= 100: notes.append(f"Mismatch: {od} run game #{ro['rushO'][o]} vs {dd} run defense #{rd['rushD'][d]}")
        nt(th, ta, g["home"], g["away"]); nt(ta, th, g["away"], g["home"])
        games.append({"id": g["id"], "home": g["home"], "away": g["away"], "neutral": g["neutral"], "pmHomeMargin": r1(pmm), "claudeHomeMargin": g["claudeHomeMargin"],
                      "vegasHomeSpread": g["vegasHomeSpread"], "pmVsClaude": r1(pmm - g["claudeHomeMargin"]), "notes": notes,
                      "qb": {g["home"]: qbinfo[th].get("starter"), g["away"]: qbinfo[ta].get("starter")}})
    games.sort(key=lambda x: -abs(x["pmVsClaude"] or 0))
    # ---- rest-of-season projections for every FBS team (same math as the main tracker's Road ahead) ----
    from math import erf, sqrt
    phi = lambda z: 0.5 * (1 + erf(z / sqrt(2)))
    CPd = {r["team"]: r["claudePower"] for r in rows}
    sched = load(year, "games") or []
    outlook = {}
    for t in tl:
        dn = cf2dash[t]
        if dn not in PMd: continue
        w = l = 0; rest = []
        for g in sched:
            if g.get("seasonType") != "regular" or t not in (g["homeTeam"], g["awayTeam"]): continue
            home = g["homeTeam"] == t; opp = g["awayTeam"] if home else g["homeTeam"]
            if g.get("completed") and g.get("homePoints") is not None:
                m = (g["homePoints"] - g["awayPoints"]) * (1 if home else -1)
                w += m > 0; l += m < 0; continue
            if g["week"] < week: continue
            od = cf2dash.get(opp, opp); fbs_opp = opp in cf2dash
            hfa = 0 if g.get("neutralSite") else (HFA if home else -HFA)
            pm_m = PMd[dn] - (PMd.get(od, FCS) if fbs_opp else FCS) + hfa
            cl_m = CPd[dn] - (CPd.get(od, FCS) if fbs_opp else FCS) + hfa
            rest.append({"id": str(g["id"]), "w": g["week"], "date": (g.get("startDate") or "")[:10], "opp": od, "fcs": not fbs_opp,
                         "site": "neutral" if g.get("neutralSite") else "home" if home else "away",
                         "pmWin": round(100 * phi(pm_m / SD), 1), "pmMargin": r1(pm_m), "claudeWin": round(100 * phi(cl_m / SD), 1)})
        rest.sort(key=lambda x: (x["w"], x["date"]))
        ep = sum(x["pmWin"] for x in rest) / 100; ec = sum(x["claudeWin"] for x in rest) / 100
        outlook[dn] = {"record": f"{w}-{l}", "pmProjW": round(w + ep, 1), "pmProjL": round(l + len(rest) - ep, 1),
                       "claudeProjW": round(w + ec, 1), "claudeProjL": round(l + len(rest) - ec, 1), "games": rest}
    for x in out_top:
        o = outlook.get(x["team"])
        if o:
            n = round(o["pmProjW"] + o["pmProjL"]); wr = int(o["pmProjW"] + 0.5)  # round half up, losses = games left over
            x["pmProj"] = f"{wr}-{n - wr}"
    cards = {}
    for dn in set(x["team"] for x in out_top) | {g["home"] for g in games} | {g["away"] for g in games}:
        if dn in d2c: cards[dn] = team_card(dn)
    doc = {"season": year, "week": week, "sortKey": year * 100 + week, "label": f"Week {week}", "throughWeek": week - 1,
           "weights": {"claudePower": W_CLAUDE, "unitPower": W_UNIT, "qbShrink": QB_SHRINK, "matchups": 0},
           "replacementQbEpa": r3(repl), "injurySource": inj.get("source"), "top25": out_top, "games": games, "teams": cards, "outlook": outlook,
           "outlookMethod": f"Win % for every remaining regular-season game = normal CDF((power gap + {HFA} home field) / {SD}), the same math as the main tracker. Player Model uses PM power; Claude Power uses Claude Power alone (the main tracker's Road ahead uses blended power, so its numbers can differ slightly). FCS opponents count as {FCS}. Projected record = current record + the sum of remaining win chances.",
           "backtest": {"note": "Fit on 2024 (weeks 4+), tested on 2025 (weeks 4+), every team's numbers rebuilt from games before each matchup.",
                        "margins": [["Vegas closing line", 11.79], ["Results-only ratings", 12.81], ["Efficiency (unit EPA) only", 13.01], ["Results + efficiency blend", 12.75], ["+ matchup & QB features", 12.75]],
                        "matchupCorr": [["Run-heavy offense vs front-seven havoc", -0.02, 0.01], ["Run-heavy offense vs run-stuffing defense", 0.08, 0.01], ["Weak protection vs pass rush", -0.07, -0.04], ["Pass-heavy offense vs DB havoc", -0.03, -0.03], ["QB recent form after a QB change", -0.20, -0.10]],
                        "totals": "No matchup feature predicted total points vs the closing over/under either (2025 test).",
                        "verdict": "Matchup interactions carry zero weight; QB changes and injuries are the player effects that move the rating."},
           "method": __doc__.strip()}
    os.makedirs(os.path.join(ROOT, "model", "out"), exist_ok=True)
    p = os.path.join(ROOT, "model", "out", f"playermodel_{year}_w{week:02d}.json")
    json.dump(doc, open(p, "w"), separators=(",", ":"))
    return doc, p


if __name__ == "__main__":
    y, w = int(sys.argv[1]), int(sys.argv[2])
    doc, p = main(y, w, sys.argv[3] if len(sys.argv) > 3 else None)
    print(p, os.path.getsize(p), "bytes")
    for x in doc["top25"]: print(x["rank"], x["team"], "pm", x["pm"], "(claude", x["claudePower"], "unit", x["unitPower"], "qb", x["qbAdj"], "inj", x["injAdj"], ") claudeRank", x["claudeRank"])
    print("games", len(doc["games"]), "teams", len(doc["teams"]))
    for g in doc["games"][:6]: print(g["away"], "@", g["home"], "PM", g["pmHomeMargin"], "Claude", g["claudeHomeMargin"], "Vegas", g["vegasHomeSpread"], g["notes"][:2])
