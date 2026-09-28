"""OOF tahminleriyle en iyi LightGBM/CatBoost ağırlığını bulur.
Kullanım: python blend.py pevpsubmition2  ->  pevpsubmition2.csv"""
import sys

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

y = (pd.read_csv("train.csv", usecols=["Will_Buy_EV"]).Will_Buy_EV == "Yes").to_numpy()
oof = {n: np.load(f"oof_{n}.npy") for n in ("lgbm", "cat")}
pred = {n: np.load(f"pred_{n}.npy") for n in ("lgbm", "cat")}

score, w = max((roc_auc_score(y, w * oof["lgbm"] + (1 - w) * oof["cat"]), w)
               for w in np.linspace(0, 1, 21))
print(f"lgbm ağırlığı {w:.2f}, harman CV AUC: {score:.5f}")

sub = pd.read_csv("sample_submission.csv")
sub["Will_Buy_EV"] = w * pred["lgbm"] + (1 - w) * pred["cat"]
sub.to_csv(f"{sys.argv[1]}.csv", index=False)
print(sub.shape, sub.head(3), sep="\n")
