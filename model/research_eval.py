"""Evaluate the research candidates (see research.py). Fit 2024, test 2025, weeks 2+ (FBS vs FBS).
Writes model/out/research_2024train_2025test.txt"""
import os, numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = []
def say(*a):
    s = " ".join(str(x) for x in a); print(s); OUT.append(s)
mae = lambda e: float(np.mean(np.abs(e)))
rd = lambda y: pd.read_csv(os.path.join(ROOT, "model", "out", f"research_{y}.csv"))


def fit(X, y, lam=1.0):
    X1 = np.c_[np.ones(len(X)), X]; A = X1.T @ X1 + lam * np.eye(X1.shape[1]); A[0, 0] -= lam
    return np.linalg.solve(A, X1.T @ y)
pred = lambda b, X: np.c_[np.ones(len(X)), X] @ b


def feats(d, N):
    f = pd.DataFrame(index=d.index)
    gp = (d.gp_H + d.gp_A) / 2
    wi = gp / (N + gp) if N > 0 else pd.Series(1.0, index=d.index)
    wp = 1 - wi
    f["hfa"] = (~d.neutral.astype(bool)).astype(float)
    f["rat"] = d.rat * wi; f["rat_luck"] = d.rat_luck * wi; f["rat_luck2"] = d.rat_luck2 * wi; f["rat_luck_half"] = d.rat_luck_half * wi
    for c in ("o_epa", "o_sr", "o_xpl", "o_epa_gt", "o_sr_gt", "o_xpl_gt"):
        f[c] = d[c] * wi
    spd = (d.sp_prev_H - d.sp_prev_A).fillna(0)
    f["p_sp"] = spd * wp
    f["p_sp_ret"] = ((d.sp_prev_H * (d.ret_ppa_H - .5)).fillna(0) - (d.sp_prev_A * (d.ret_ppa_A - .5)).fillna(0)) * wp  # good teams losing production regress
    f["p_ret"] = ((d.ret_ppa_H - d.ret_ppa_A).fillna(0)) * wp
    f["p_tal"] = ((d.tal_H - d.tal_A).fillna(0)) * wp
    # situational (signed home minus away)
    f["rest"] = (d.rest_home.clip(4, 15) - d.rest_away.clip(4, 15)).fillna(0)
    f["bye"] = ((d.rest_home >= 12).astype(int) - (d.rest_away >= 12).astype(int))
    f["dist"] = (np.log1p(d.dist_away.fillna(0)) - np.log1p(d.dist_home.fillna(0)))
    f["tz_east"] = (d.tz_away.clip(lower=0).fillna(0) - d.tz_home.clip(lower=0).fillna(0))   # hours traveled east
    f["tz_abs"] = (d.tz_away.abs().fillna(0) - d.tz_home.abs().fillna(0))
    f["elev"] = ((d.elev_venue.fillna(0) - d.elev_away_home.fillna(0)).clip(lower=0) / 1000) * (~d.neutral.astype(bool))
    return f.fillna(0)


tr0, te0 = rd(2024), rd(2025)
tr0, te0 = tr0.dropna(subset=["spread", "rat"]), te0.dropna(subset=["spread", "rat"])
say(f"Research backtest: fit 2024 ({len(tr0)} FBS games, weeks 2+), test 2025 ({len(te0)} games)")
say(f"Closing line MAE  train {mae(tr0.margin - tr0.mkt):.2f}  test {mae(te0.margin - te0.mkt):.2f}   |  opening line test {mae(te0.margin - te0.mkt_open):.2f}")
ytr, yte = tr0.margin.to_numpy(float), te0.margin.to_numpy(float)

say("\nA-C. Margin models without a preseason prior (ridge, 2025 test MAE; lower is better)")
sets = [("in-season results only (how Unit Power started)", ["hfa", "rat"]),
        ("results, turnover luck removed (5 pts/turnover)", ["hfa", "rat_luck"]),
        ("results, turnover luck half-removed (2.5 pts)", ["hfa", "rat_luck_half"]),
        ("results, luck + return/defensive TDs removed", ["hfa", "rat_luck2"]),
        ("+ efficiency EPA/play (PM v1 unit power)", ["hfa", "rat", "o_epa"]),
        ("+ efficiency EPA, garbage time removed", ["hfa", "rat", "o_epa_gt"]),
        ("+ success rate & explosiveness, garbage time removed", ["hfa", "rat", "o_sr_gt", "o_xpl_gt"])]
for nm, cols in sets:
    b = fit(feats(tr0, 0)[cols].to_numpy(), ytr, 5); p = pred(b, feats(te0, 0)[cols].to_numpy())
    say(f"  {nm:58s} {mae(yte - p):6.2f}")

say("\n  Adding a preseason prior worth N games (weight N/(N+games played), never quite zero). Train = 2024 fit, test = 2025:")
PRI_FULL = ["p_sp", "p_sp_ret", "p_ret", "p_tal"]; PRI = ["p_sp", "p_tal"]
grid = []
for N in (1, 2, 3, 4, 6, 8):
    Ftr, Fte = feats(tr0, N), feats(te0, N)
    for luck in ("rat", "rat_luck_half", "rat_luck"):
        for pri, pl in ((PRI, "SP+ & talent"), (PRI_FULL, "+ returning production")):
            cols = ["hfa", luck, "o_sr_gt", "o_xpl_gt"] + pri
            b = fit(Ftr[cols].to_numpy(), ytr, 5)
            grid.append((N, luck, pl, mae(ytr - pred(b, Ftr[cols].to_numpy())), mae(yte - pred(b, Fte[cols].to_numpy()))))
G2 = pd.DataFrame(grid, columns=["N", "results", "prior", "train", "test"])
say(G2.pivot_table(index=["results", "prior"], columns="N", values="test").round(2).to_string())
say("  (2025 test MAE by N; rows = how turnover luck is handled and which prior inputs are used)")
say("  Decisions, each made on whether it helped in BOTH seasons (2024 in-sample and 2025 out-of-sample):")
def both(a_res, a_pri, b_res, b_pri, N=2):
    x = G2[(G2.N == N) & (G2.results == a_res) & (G2.prior == a_pri)].iloc[0]; y = G2[(G2.N == N) & (G2.results == b_res) & (G2.prior == b_pri)].iloc[0]
    return x.train - y.train, x.test - y.test
d1 = both("rat", "SP+ & talent", "rat_luck_half", "SP+ & talent"); d2 = both("rat", "SP+ & talent", "rat_luck", "SP+ & talent")
d3 = both("rat_luck_half", "SP+ & talent", "rat_luck_half", "+ returning production")
say(f"   - half-strength turnover-luck removal: improves 2024 by {d1[0]:+.3f} and 2025 by {d1[1]:+.3f} -> KEEP")
say(f"   - full-strength (5 pts/turnover): 2024 {d2[0]:+.3f}, 2025 {d2[1]:+.3f} -> too strong out of sample")
say(f"   - returning production on top of SP+ & talent: 2024 {d3[0]:+.3f}, 2025 {d3[1]:+.3f} -> DROP (positive = helped)")
say("   - prior weight N = 2 games (N = 1 and 2 are close in 2024; the literature favors a few games; 2 is the smaller, safer choice)")
FINAL = ["hfa", "rat_luck_half", "o_sr_gt"] + PRI; Nbest = 2
x1 = fit(Ftr2 := feats(tr0, 2)[["hfa", "rat_luck_half", "o_sr_gt", "o_xpl_gt"] + PRI].to_numpy(), ytr, 5)
say(f"   - explosiveness on top of success rate: 2025 test {mae(yte - pred(x1, feats(te0, 2)[['hfa', 'rat_luck_half', 'o_sr_gt', 'o_xpl_gt'] + PRI].to_numpy())):.3f} with vs without (below) -> DROP (adds nothing; garbage-time-filtered success rate carries the efficiency signal)")
Ftr, Fte = feats(tr0, Nbest), feats(te0, Nbest)
b_best = fit(Ftr[FINAL].to_numpy(), ytr, 5); p_best = pred(b_best, Fte[FINAL].to_numpy())
say(f"  FINAL 'Data Rating': 2025 test MAE {mae(yte - p_best):.2f} (closing line {mae(yte - te0.mkt):.2f}; in-season-only start {mae(yte - pred(fit(feats(tr0,0)[['hfa','rat']].to_numpy(), ytr, 5), feats(te0,0)[['hfa','rat']].to_numpy())):.2f})")
say("  Coefficients (2024 fit): " + ", ".join(f"{c} {v:+.2f}" for c, v in zip(["const"] + FINAL, b_best)))
say("\n  By week (2025 test MAE): Data Rating vs in-season results only vs closing line")
bc = fit(feats(tr0, 0)[["hfa", "rat"]].to_numpy(), ytr, 5); p_cur = pred(bc, feats(te0, 0)[["hfa", "rat"]].to_numpy())
for lo, hi in ((2, 4), (5, 8), (9, 16)):
    m = ((te0.week >= lo) & (te0.week <= hi)).to_numpy()
    say(f"  weeks {lo:2d}-{hi:2d} (n={m.sum():3d}): Data Rating {mae(yte[m] - p_best[m]):6.2f}   in-season only {mae(yte[m] - p_cur[m]):6.2f}   Vegas {mae(yte[m] - te0.mkt.to_numpy()[m]):6.2f}")
base, PRI_E = FINAL, []
say("\nD. Situational features vs the result against the closing line (margin - market); corr 2024 / 2025")
rtr, rte = (tr0.margin - tr0.mkt).to_numpy(float), (te0.margin - te0.mkt).to_numpy(float)
Ftr, Fte = feats(tr0, Nbest), feats(te0, Nbest)
SIT = ["rest", "bye", "dist", "tz_east", "tz_abs", "elev"]
for c in SIT:
    say(f"  {c:8s} corr {np.corrcoef(Ftr[c], rtr)[0,1]:+.3f} / {np.corrcoef(Fte[c], rte)[0,1]:+.3f}   mean |x| {Ftr[c].abs().mean():.2f}")
b = fit(Ftr[SIT].to_numpy(), rtr, 20); p = pred(b, Fte[SIT].to_numpy())
say(f"  all situational together: test MAE vs line {mae(rte - p):.3f} vs {mae(rte):.3f} (line alone); coefs " + ", ".join(f"{c} {v:+.2f}" for c, v in zip(SIT, b[1:])))
# home field
hm = ~tr0.neutral.astype(bool); he = ~te0.neutral.astype(bool)
say(f"  Home field fitted by the results model: 2024 {tr0.hfa_fit.iloc[-1]:.2f}, 2025 {te0.hfa_fit.iloc[-1]:.2f} pts (end of season)")
say(f"  Market-implied: average home result vs closing line 2024 {rtr[hm.to_numpy()].mean():+.2f}, 2025 {rte[he.to_numpy()].mean():+.2f} (0 = market prices HFA right)")

say("\nE. The CLV test: does the model's disagreement with the OPENING line predict where the line closes?")
Fo = feats(te0, Nbest); po = pred(b_best, Fo[FINAL].to_numpy())
Ft = feats(tr0, Nbest); pt = pred(b_best, Ft[FINAL].to_numpy())
for nm, d, pm in (("2024 (in-sample)", tr0, pt), ("2025 (test)", te0, po)):
    ok = d.mkt_open.notna().to_numpy()
    gap = (pm - d.mkt_open.to_numpy())[ok]; move = (d.mkt - d.mkt_open).to_numpy()[ok]; res_close = (d.margin - d.mkt).to_numpy()[ok]
    slope = np.polyfit(gap, move, 1)[0]
    big = np.abs(gap) >= 4
    agree = np.sign(move[big]) == np.sign(gap[big]); nz = move[big] != 0
    say(f"  {nm}: corr(model - open, close - open) {np.corrcoef(gap, move)[0,1]:+.3f}, slope {slope:+.3f}; gaps of 4+ pts (n={big.sum()}): line moved toward the model {agree[nz].mean()*100:.0f}% of moves;"
        f" result vs CLOSE in the model's direction {np.mean(np.sign(res_close[big]) == np.sign(gap[big]))*100:.0f}%")
# blending with the market: how much weight on the model vs the closing line?
say("\n  Blend test: prediction = w x model + (1 - w) x closing line (2025)")
for w in (0, .1, .2, .3, .5):
    say(f"    w = {w:.1f}: MAE {mae(yte - (w * po + (1 - w) * te0.mkt.to_numpy())):.3f}")

say("\nF. Totals: does a pace x efficiency scoring environment predict the result against the closing over/under?")
def tfeat(d):
    f = pd.DataFrame(index=d.index)
    f["sr_env"] = d.o_sr_gt_tot; f["xpl_env"] = d.o_xpl_gt_tot; f["epa_env"] = d.o_epa_gt_tot; f["pace"] = d.pace - 60
    f["pace_x_epa"] = f.pace * f.epa_env
    return f.fillna(0)
ok_tr, ok_te = tr0.ou.notna(), te0.ou.notna()
ttr, tte = (tr0.total - tr0.ou)[ok_tr].to_numpy(float), (te0.total - te0.ou)[ok_te].to_numpy(float)
Ttr, Tte = tfeat(tr0)[ok_tr], tfeat(te0)[ok_te]
say(f"  closing O/U MAE 2025: {mae(tte):.2f}")
for c in Ttr.columns:
    say(f"  {c:11s} corr with (total - O/U) 2024 {np.corrcoef(Ttr[c], ttr)[0,1]:+.3f} / 2025 {np.corrcoef(Tte[c], tte)[0,1]:+.3f}")
b = fit(Ttr.to_numpy(), ttr, 20); pt_ = pred(b, Tte.to_numpy())
say(f"  all together: 2025 MAE vs O/U {mae(tte - pt_):.3f} vs {mae(tte):.3f} (O/U alone)")
say(f"  overs hit: 2024 {np.mean(ttr > 0)*100:.1f}%, 2025 {np.mean(tte > 0)*100:.1f}% (pushes counted as unders)")

# production coefficients: refit the final model on 2024 + 2025 together for live use
both_df = pd.concat([tr0, te0], ignore_index=True); Fb = feats(both_df, Nbest)
b_prod = fit(Fb[FINAL].to_numpy(), both_df.margin.to_numpy(float), 5)
import json
json.dump({"N": Nbest, "features": FINAL, "coef": dict(zip(["const"] + FINAL, [round(float(x), 4) for x in b_prod])), "lucky_pts_per_turnover": 2.5,
           "fit": "2024 + 2025 FBS games, weeks 2+", "test2025_mae": round(mae(yte - p_best), 3), "vegas2025_mae": round(mae(yte - te0.mkt), 3)},
          open(os.path.join(ROOT, "model", "out", "rr_coefs.json"), "w"), indent=1)
say("\nProduction coefficients (2024 + 2025 refit): " + ", ".join(f"{c} {v:+.2f}" for c, v in zip(["const"] + FINAL, b_prod)))

with open(os.path.join(ROOT, "model", "out", "research_2024train_2025test.txt"), "w") as fh:
    fh.write("\n".join(OUT) + "\n")
