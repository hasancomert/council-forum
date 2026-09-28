"""Predicting EV Purchases (Playground S6E9): LightGBM + CatBoost, 5-fold CV, AUC."""
import sys

import numpy as np
import pandas as pd
import lightgbm as lgb
from catboost import CatBoostClassifier
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold

SEED, FOLDS, TARGET = 42, 5, "Will_Buy_EV"
CATS = ["Gender", "City_Type", "Current_Car_Type", "Home_Charging_Possible",
        "Subsidy_Available", "Range_Anxiety_Level"]

train = pd.read_csv("train.csv")
test = pd.read_csv("test.csv")
y = (train.pop(TARGET) == "Yes").astype(int).to_numpy()
features = [c for c in train.columns if c != "id"]


def prepare(df):
    df = df[features].copy()
    for c in CATS:
        df[c] = pd.Categorical(df[c], categories=sorted(train[c].unique()))
    return df


X, X_test = prepare(train), prepare(test)
folds = list(StratifiedKFold(FOLDS, shuffle=True, random_state=SEED).split(X, y))


def run(name, fit_predict):
    oof, pred = np.zeros(len(X)), np.zeros(len(X_test))
    for i, (tr, va) in enumerate(folds):
        oof[va], p = fit_predict(X.iloc[tr], y[tr], X.iloc[va], y[va])
        pred += p / FOLDS
        print(f"{name} fold {i}: {roc_auc_score(y[va], oof[va]):.5f}", flush=True)
    print(f"{name} CV AUC: {roc_auc_score(y, oof):.5f}", flush=True)
    return oof, pred


def lgbm(Xtr, ytr, Xva, yva):
    m = lgb.LGBMClassifier(n_estimators=5000, learning_rate=0.03, num_leaves=63,
                           min_child_samples=100, subsample=0.8, subsample_freq=1,
                           colsample_bytree=0.7, reg_lambda=1.0, random_state=SEED,
                           verbose=-1)
    m.fit(Xtr, ytr, eval_set=[(Xva, yva)], eval_metric="auc",
          callbacks=[lgb.early_stopping(200, verbose=False)])
    return m.predict_proba(Xva)[:, 1], m.predict_proba(X_test)[:, 1]


def cat(Xtr, ytr, Xva, yva):
    to_str = lambda d: d.astype({c: str for c in CATS})
    m = CatBoostClassifier(iterations=5000, learning_rate=0.08, depth=6,
                           eval_metric="AUC", od_type="Iter", od_wait=200,
                           cat_features=CATS, random_seed=SEED, verbose=0,
                           thread_count=-1)
    m.fit(to_str(Xtr), ytr, eval_set=(to_str(Xva), yva))
    return m.predict_proba(to_str(Xva))[:, 1], m.predict_proba(to_str(X_test))[:, 1]


models = {"lgbm": lgbm, "cat": cat}
names = sys.argv[1:] or list(models)
results = {n: run(n, models[n]) for n in names}
for n, (oof, pred) in results.items():
    np.save(f"oof_{n}.npy", oof)
    np.save(f"pred_{n}.npy", pred)
