"""Do matchup features predict TOTAL points vs the closing over/under? Fit 2024, test 2025."""
import os, numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
rd = lambda y: pd.read_csv(os.path.join(ROOT, "model", "out", f"games_{y}.csv")).dropna(subset=["ou"])
def feats(d):
    f = pd.DataFrame(index=d.index); lg = d.rr_lg
    # sums (both sides) — a disruptive front vs a run-heavy offense should suppress scoring for that offense
    f["run_vs_f7"] = (d.rr_H - lg) * d.o_f7havoc_defA + (d.rr_A - lg) * d.o_f7havoc_defH
    f["run_vs_stuff"] = (d.rr_H - lg) * d.o_stuff_defA + (d.rr_A - lg) * d.o_stuff_defH
    f["ol_vs_rush"] = ((1 - d.rr_H) * d.o_sack_rate_offH * d.o_sack_rate_defA + (1 - d.rr_A) * d.o_sack_rate_offA * d.o_sack_rate_defH) * 100
    f["pass_vs_db"] = (1 - d.rr_H) * d.o_dbhavoc_defA + (1 - d.rr_A) * d.o_dbhavoc_defH
    f["f7_sum"] = d.o_f7havoc_defA + d.o_f7havoc_defH
    f["epa_sum"] = (d.o_epa_H + d.o_epa_A) * 70
    f["rush_rate_sum"] = d.rr_H + d.rr_A - 2 * lg
    return f.fillna(0)
def fit(X, y, lam=5.0):
    X1 = np.c_[np.ones(len(X)), X]; A = X1.T @ X1 + lam * np.eye(X1.shape[1]); A[0, 0] -= lam
    return np.linalg.solve(A, X1.T @ y)
pred = lambda b, X: np.c_[np.ones(len(X)), X] @ b
mae = lambda e: float(np.mean(np.abs(e)))
tr, te = rd(2024), rd(2025); Ftr, Fte = feats(tr), feats(te)
ytr, yte = (tr.total - tr.ou).to_numpy(float), (te.total - te.ou).to_numpy(float)
print(f"totals: train {len(tr)}, test {len(te)}; closing O/U MAE test {mae(yte):.2f}; overs hit {np.mean(yte>0):.3f} (2025)")
for c in Ftr.columns:
    b = fit(Ftr[[c]].to_numpy(), ytr); p = pred(b, Fte[[c]].to_numpy())
    print(f"  {c:14s} coef {b[1]:+9.2f}  corr train {np.corrcoef(Ftr[c], ytr)[0,1]:+.3f}  test {np.corrcoef(Fte[c], yte)[0,1]:+.3f}  test MAE {mae(yte-p):.3f}")
cols = ["run_vs_f7", "run_vs_stuff", "ol_vs_rush", "pass_vs_db"]
b = fit(Ftr[cols].to_numpy(), ytr); p = pred(b, Fte[cols].to_numpy())
print(f"  all matchup features: test MAE {mae(yte - p):.3f} vs {mae(yte):.3f}")
# betting-style check: when the model says under by 3+, how did unders do?
for thr in (2, 3):
    sel = p <= -thr
    print(f"  model says under by {thr}+: n={int(sel.sum())}, unders hit {np.mean(yte[sel] < 0) if sel.any() else float('nan'):.3f}")
