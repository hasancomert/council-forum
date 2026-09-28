# Kaggle: Predicting Electric Vehicle Purchases (Playground S6E9)

Hedef `Will_Buy_EV` (Yes/No), gönderim olasılık. Metrik ROC AUC varsayıldı.
Forum projesinden bağımsız; yalnızca bu klasör.

## Çalıştırma
Yarışma zip'indeki `train.csv`, `test.csv`, `sample_submission.csv` bu klasöre (Git'e girmez).

```
python -m pip install -r requirements.txt
python train.py              # lgbm + cat, 5 kat; oof_*.npy ve pred_*.npy yazar
python train.py lgbm         # yalnızca biri
python blend.py pevpsubmition2
```

## Gönderimler
| No | İçerik | CV AUC | Public LB |
|---|---|---|---|
| 1 | LightGBM 0.6 + CatBoost 0.4 (olasılık ortalaması), ham özellikler | 0.94201 | 0.94176 |

Tek modeller (1. gönderim): LightGBM 0.94190 (~3 dk), CatBoost 0.94178 (~22 dk, 4 çekirdek CPU).
