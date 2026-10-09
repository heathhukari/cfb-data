"""Out-of-sample test: do player/unit matchup features improve on (a) the closing line and (b) a ratings model?
Train on 2024 (weeks 4+), test on 2025 (weeks 4+)."""
import os, numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
rd = lambda y: pd.read_csv(os.path.join(ROOT, "model", "out", f"games_{y}.csv"))


def feats(d):
    f = pd.DataFrame(index=d.index)
    lg = d.rr_lg
    f["eff"] = (d.o_epa_H - d.o_epa_A) * 70                       # efficiency margin (pts-ish)
    f["hfa"] = (~d.neutral).astype(float)
    f["run_vs_f7"] = (d.rr_H - lg) * d.o_f7havoc_defA - (d.rr_A - lg) * d.o_f7havoc_defH
    f["run_vs_stuff"] = (d.rr_H - lg) * d.o_stuff_defA - (d.rr_A - lg) * d.o_stuff_defH
    f["ol_vs_rush"] = (1 - d.rr_H) * d.o_sack_rate_offH * d.o_sack_rate_defA * 100 - (1 - d.rr_A) * d.o_sack_rate_offA * d.o_sack_rate_defH * 100
    f["pass_vs_db"] = (1 - d.rr_H) * d.o_dbhavoc_defA - (1 - d.rr_A) * d.o_dbhavoc_defH
    f["rush_unit"] = d.rr_H * (d.o_rush_epa_H) - d.rr_A * (d.o_rush_epa_A)
    f["pass_unit"] = (1 - d.rr_H) * d.o_pass_epa_H - (1 - d.rr_A) * d.o_pass_epa_A
    f["qb_form"] = (d.qb_last_H - d.qb_season_H).fillna(0) * d.att_pg_H.fillna(30) - (d.qb_last_A - d.qb_season_A).fillna(0) * d.att_pg_A.fillna(30)
    return f.fillna(0)


def fit(X, y, lam=1.0):
    X1 = np.c_[np.ones(len(X)), X]; A = X1.T @ X1 + lam * np.eye(X1.shape[1]); A[0, 0] -= lam
    return np.linalg.solve(A, X1.T @ y)


def pred(b, X): return np.c_[np.ones(len(X)), X] @ b
mae = lambda e: float(np.mean(np.abs(e)))

tr, te = rd(2024), rd(2025)
tr, te = tr.dropna(subset=["mkt", "rat"]), te.dropna(subset=["mkt", "rat"])
Ftr, Fte = feats(tr), feats(te)
MATCH = ["run_vs_f7", "run_vs_stuff", "ol_vs_rush", "pass_vs_db", "qb_form"]
print(f"train {len(tr)} games (2024), test {len(te)} games (2025)")
print(f"closing line MAE: train {mae(tr.margin - tr.mkt):.2f}  test {mae(te.margin - te.mkt):.2f}")
# (b) ratings-style model without / with matchup features
base_cols = ["eff", "hfa"]
for name, cols in [("ratings: points model only", None), ("ratings: points + efficiency", base_cols), ("ratings + efficiency + unit split", base_cols + ["rush_unit", "pass_unit"]),
                   ("... + matchup & QB features", base_cols + ["rush_unit", "pass_unit"] + MATCH)]:
    if cols is None:
        print(f"{name:42s} test MAE {mae(te.margin - te.rat):.2f}"); continue
    Xtr = np.c_[tr.rat, Ftr[cols]]; Xte = np.c_[te.rat, Fte[cols]]
    b = fit(Xtr, tr.margin.to_numpy(float), lam=5)
    print(f"{name:42s} test MAE {mae(te.margin - pred(b, Xte)):.2f}   (train {mae(tr.margin - pred(b, Xtr)):.2f})")
# (a) residual vs the closing line
print("\nResidual vs closing line (margin - market): does anything predict it out of sample?")
ytr, yte = (tr.margin - tr.mkt).to_numpy(float), (te.margin - te.mkt).to_numpy(float)
for c in MATCH + ["rush_unit", "pass_unit", "eff"]:
    b = fit(Ftr[[c]].to_numpy(), ytr, lam=5); p = pred(b, Fte[[c]].to_numpy())
    r_tr = np.corrcoef(Ftr[c], ytr)[0, 1]; r_te = np.corrcoef(Fte[c], yte)[0, 1]
    print(f"  {c:14s} coef {b[1]:+8.2f}  corr train {r_tr:+.3f}  test {r_te:+.3f}  test MAE {mae(yte - p):.3f} vs {mae(yte):.3f} (line alone)")
b = fit(Ftr[MATCH].to_numpy(), ytr, lam=5); p = pred(b, Fte[MATCH].to_numpy())
print(f"  all matchup features: test MAE {mae(yte - p):.3f} vs {mae(yte):.3f}; coefs {np.round(b[1:], 2)}")
# QB change subset
for nm, d, F, y in (("2024", tr, Ftr, ytr), ("2025", te, Fte, yte)):
    m = (d.qb_change_H == 1) | (d.qb_change_A == 1)
    print(f"  QB-change games {nm}: n={int(m.sum())}, corr(qb_form, residual)={np.corrcoef(F.qb_form[m], y[m.to_numpy()])[0,1]:+.3f}")
