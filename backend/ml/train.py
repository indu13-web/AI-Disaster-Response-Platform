"""
train.py
--------
Trains regression models for the ResQ Disaster Response Resource Demand Prediction Engine
using REAL historical disaster events from USGS (2015-2024) calibrated via Sphere Humanitarian Standards.

Methodology:
- Targets: ['food_packets', 'water_litres', 'medical_kits', 'shelter_capacity_persons']
- Baseline Features: ['disaster_type', 'affected_population', 'severity', 'affected_buildings']
  * Demographic percentages (elderly, children, medical_dependent) are intentionally EXCLUDED
    from baseline features to prevent double-counting when the downstream Day 3 vulnerability
    adjustment module is integrated.
- Target transformation: log1p(y) during training, expm1(y) during inference, clipped at 0.
- Model architecture: GradientBoostingRegressor with OneHotEncoder via ColumnTransformer Pipeline.
- Data split: 60% Train, 20% Calibration, 20% Test (fixed random state 42).
- Naive baseline: Predicts training set mean (evaluated on test set in original units).
- Prediction intervals: Split Conformal Prediction.
  * Absolute residuals evaluated on Calibration set: R_i = |y_cal - pred_cal|.
  * Conformal quantile q_hat computed at ceil((n_cal + 1) * (1 - alpha)) / n_cal with alpha = 0.10 (nominal 90%).
  * Prediction interval: [max(0, pred - q_hat), pred + q_hat].
  * Empirical coverage computed and reported on Test set.
  * Clearly labelled: "empirical prediction interval, nominal 90%, calibrated on real historical USGS data with Sphere standards; not a validated real-world confidence level".
- Artifacts: Saved per-resource joblib pipelines, conformal quantiles, and a comprehensive metrics.json.
"""

import os
import math
import json
from datetime import datetime, timezone
import numpy as np
import pandas as pd
import joblib

from sklearn.model_selection import train_test_split
from sklearn.preprocessing import OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error

TARGET_RESOURCES = [
    "food_packets",
    "water_litres",
    "medical_kits",
    "shelter_capacity_persons",
]

RESOURCE_UNITS = {
    "food_packets": "packets (1 packet = 1 person-day meal)",
    "water_litres": "litres (Sphere standard: drinking, cooking, hygiene)",
    "medical_kits": "kits (standard emergency/trauma first-aid kits)",
    "shelter_capacity_persons": "people (displaced persons requiring shelter space)",
}

BASELINE_FEATURES = [
    "disaster_type",
    "affected_population",
    "severity",
    "affected_buildings",
]

def load_dataset(csv_path: str) -> pd.DataFrame:
    if not os.path.isfile(csv_path):
        raise FileNotFoundError(
            f"Required training dataset not found at '{csv_path}'. "
            f"Please run 'fetch_real_historical_data.py' first."
        )
    df = pd.read_csv(csv_path)
    print(f"[Data Loader] Successfully loaded {len(df)} rows from {os.path.basename(csv_path)}")
    return df

def train_models():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_path = os.path.join(script_dir, "data", "REAL_HISTORICAL_USGS_resource_demand_training.csv")
    artifacts_dir = os.path.join(script_dir, "artifacts")
    os.makedirs(artifacts_dir, exist_ok=True)

    df = load_dataset(data_path)

    # Validate presence of expected columns
    for col in BASELINE_FEATURES + TARGET_RESOURCES:
        if col not in df.columns:
            raise ValueError(f"Missing expected column '{col}' in training dataset.")

    # 60% Train, 20% Calibration, 20% Test
    df_train, df_temp = train_test_split(df, test_size=0.40, random_state=42)
    df_cal, df_test = train_test_split(df_temp, test_size=0.50, random_state=42)

    n_train = len(df_train)
    n_cal = len(df_cal)
    n_test = len(df_test)

    print(f"[Data Splits] Total: {len(df)} | Train: {n_train} (60%) | Cal: {n_cal} (20%) | Test: {n_test} (20%)")

    X_train = df_train[BASELINE_FEATURES]
    X_cal = df_cal[BASELINE_FEATURES]
    X_test = df_test[BASELINE_FEATURES]

    # Preprocessing
    categorical_features = ["disaster_type"]
    numeric_features = ["affected_population", "severity", "affected_buildings"]

    preprocessor = ColumnTransformer(
        transformers=[
            ("cat", OneHotEncoder(drop="first", sparse_output=False, handle_unknown="ignore"), categorical_features),
            ("num", "passthrough", numeric_features),
        ]
    )

    alpha = 0.10  # Nominal 90% coverage
    k = math.ceil((n_cal + 1) * (1.0 - alpha))
    conformal_quantile_level = min(1.0, k / n_cal)

    metrics_output = {
        "model_name": "ResQ Resource Demand Regression Engine",
        "model_version": "historical-usgs-v1.0",
        "training_date_utc": datetime.now(timezone.utc).isoformat(),
        "data_source": "REAL HISTORICAL USGS EVENTS (2015-2024) - Relief demand computed via Sphere humanitarian standards",
        "split_counts": {
            "train": n_train,
            "calibration": n_cal,
            "test": n_test,
            "total": len(df)
        },
        "features": BASELINE_FEATURES,
        "conformal_interval_settings": {
            "nominal_confidence": 0.90,
            "alpha": alpha,
            "calibration_samples": n_cal,
            "quantile_level_fraction": conformal_quantile_level,
            "interval_label": "empirical prediction interval, nominal 90%, calibrated on real historical USGS data with Sphere standards; not a validated real-world confidence level"
        },
        "resources": {}
    }

    print("\n==================================================================")
    print(" TRAINING & EVALUATION REPORT (ORIGINAL UNITS) ")
    print(" DATA SOURCE: Real Historical USGS Disaster Events (2015-2024)")
    print("==================================================================")

    for target in TARGET_RESOURCES:
        y_train_orig = df_train[target].values
        y_cal_orig = df_cal[target].values
        y_test_orig = df_test[target].values

        # Log1p transformation for training
        y_train_log = np.log1p(y_train_orig)

        # Regressor Pipeline
        regressor = GradientBoostingRegressor(
            n_estimators=100,
            learning_rate=0.08,
            max_depth=4,
            random_state=42
        )

        pipeline = Pipeline([
            ("preprocessor", preprocessor),
            ("regressor", regressor)
        ])

        pipeline.fit(X_train, y_train_log)

        # Predict on calibration set and convert back with expm1, clipping at 0
        cal_pred_log = pipeline.predict(X_cal)
        cal_preds_orig = np.clip(np.expm1(cal_pred_log), 0, None)

        # Split Conformal Prediction quantile
        cal_residuals = np.abs(y_cal_orig - cal_preds_orig)
        q_hat = float(np.quantile(cal_residuals, conformal_quantile_level, method="higher"))

        # Predict on test set
        test_pred_log = pipeline.predict(X_test)
        test_preds_orig = np.clip(np.expm1(test_pred_log), 0, None)

        # Evaluate model in ORIGINAL units
        model_mae = float(mean_absolute_error(y_test_orig, test_preds_orig))
        model_rmse = float(np.sqrt(mean_squared_error(y_test_orig, test_preds_orig)))

        # Naive Baseline: Predict training mean
        naive_mean = float(np.mean(y_train_orig))
        naive_preds = np.full_like(y_test_orig, fill_value=naive_mean)
        naive_mae = float(mean_absolute_error(y_test_orig, naive_preds))
        naive_rmse = float(np.sqrt(mean_squared_error(y_test_orig, naive_preds)))

        # Test set interval coverage
        test_lower = np.clip(test_preds_orig - q_hat, 0, None)
        test_upper = test_preds_orig + q_hat
        test_covered = (y_test_orig >= test_lower) & (y_test_orig <= test_upper)
        empirical_coverage = float(np.mean(test_covered))

        # Save model pipeline and conformal quantile
        model_filename = f"model_{target}.joblib"
        quantile_filename = f"conformal_quantile_{target}.joblib"

        joblib.dump(pipeline, os.path.join(artifacts_dir, model_filename))
        joblib.dump({"target": target, "q_hat": q_hat, "alpha": alpha}, os.path.join(artifacts_dir, quantile_filename))

        # Store metrics
        metrics_output["resources"][target] = {
            "unit": RESOURCE_UNITS[target],
            "model_mae": round(model_mae, 2),
            "model_rmse": round(model_rmse, 2),
            "naive_baseline_mae": round(naive_mae, 2),
            "naive_baseline_rmse": round(naive_rmse, 2),
            "conformal_quantile_q_hat": round(q_hat, 2),
            "test_empirical_coverage": round(empirical_coverage, 4),
            "model_file": model_filename,
            "quantile_file": quantile_filename
        }

        print(f"\nResource: [{target.upper()}] ({RESOURCE_UNITS[target]})")
        print(f"  Model Performance (Test):  MAE = {model_mae:,.2f} | RMSE = {model_rmse:,.2f}")
        print(f"  Naive Baseline (Test):     MAE = {naive_mae:,.2f} | RMSE = {naive_rmse:,.2f}")
        print(f"  Conformal Quantile (q_hat): +/- {q_hat:,.2f}")
        print(f"  Empirical Test Coverage:   {empirical_coverage * 100:.2f}% (Nominal: 90.0%)")

    # Save metrics JSON
    metrics_path = os.path.join(artifacts_dir, "metrics.json")
    with open(metrics_path, "w") as f:
        json.dump(metrics_output, f, indent=2)

    print("\n==================================================================")
    print(f" Artifacts successfully saved to: {artifacts_dir}")
    print(f" Metrics metadata recorded at: {metrics_path}")
    print("==================================================================\n")

if __name__ == "__main__":
    train_models()
