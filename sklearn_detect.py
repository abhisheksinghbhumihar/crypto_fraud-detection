"""
fraud_detection.py
═══════════════════════════════════════════════════════════════════
Fraud Detection Engine — sklearn
Tables  : clean_historical_price  |  clean_realtime_quotes
Columns : id, symbol, date, open, high, low, close, volume,
          daily_return, volatility_5d, volume_surge,
          is_suspicious, suspicion_reason, source, created_at

NEW ADDITION: Also loads fraud_million_rows.csv and stores in fraud_transactions table
"""

from __future__ import annotations

import os
import warnings
from datetime import datetime, timezone
from typing import Optional

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from loguru import logger
from sqlalchemy import create_engine, text

# sklearn
from sklearn.ensemble import IsolationForest, RandomForestClassifier, GradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    roc_auc_score,
    precision_recall_curve,
    average_precision_score,
)
from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import RobustScaler
from sklearn.utils.class_weight import compute_class_weight

# imbalanced-learn (handles class imbalance — fraud is rare)
try:
    from imblearn.over_sampling import SMOTE
    from imblearn.pipeline import Pipeline as ImbPipeline
    HAS_IMBLEARN = True
except ImportError:
    HAS_IMBLEARN = False
    logger.warning("imbalanced-learn not installed — SMOTE disabled. pip install imbalanced-learn")

warnings.filterwarnings("ignore")
load_dotenv()

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────

DB_PATH = r"C:\Users\anjal\OneDrive\Desktop\pubmed datttaaaa\fraud_detection_finance.db"
CSV_PATH = r"C:\Users\anjal\OneDrive\Desktop\pubmed datttaaaa\fraud_million_rows.csv"

# Feature columns present in both tables
BASE_FEATURES = [
    "open", "high", "low", "close", "volume",
    "daily_return", "volatility_5d", "volume_surge",
]

# Engineered features added by this script
ENGINEERED_FEATURES = [
    "price_spread_pct",      # (high - low) / low  — wide spread = suspicious
    "candle_body_pct",       # abs(close - open) / open — large body = volatile
    "upper_wick_pct",        # (high - max(open,close)) / close — wick ratio
    "lower_wick_pct",        # (min(open,close) - low) / close
    "close_vs_open",         # close / open - 1  — directional move
    "high_close_ratio",      # high / close  — how far above close the high was
    "volume_log",            # log1p(volume)  — normalize skewed volume
    "return_x_volume",       # daily_return * volume_surge — combined signal
    "volatility_x_surge",    # volatility_5d * volume_surge
    "is_gap_up",             # open > prev_close by >2%
    "is_gap_down",           # open < prev_close by >2%
]

ALL_FEATURES = BASE_FEATURES + ENGINEERED_FEATURES

LABEL_COL   = "is_suspicious"
REASON_COL  = "suspicion_reason"

# Isolation Forest contamination — expected fraction of anomalies
CONTAMINATION = 0.05   # 5% — adjust based on your domain knowledge

# Prediction threshold: ensemble score above this = fraud
FRAUD_THRESHOLD = 0.45

# Output table
OUTPUT_TABLE = "fraud_predictions"

# ─────────────────────────────────────────────────────────────────────────────
# DATABASE (SQLite)
# ─────────────────────────────────────────────────────────────────────────────

def get_engine():
    """Create SQLite engine connection"""
    return create_engine(f"sqlite:///{DB_PATH}", pool_pre_ping=True)


def load_table(engine, table_name: str) -> pd.DataFrame:
    """Load a full table into a DataFrame."""
    logger.info(f"Loading table: {table_name}")
    try:
        df = pd.read_sql(f"SELECT * FROM {table_name}", engine)
        df["_source_table"] = table_name
        logger.info(f"  → {len(df):,} rows, {df.columns.tolist()}")
    except Exception as e:
        logger.warning(f"Table {table_name} not found or error: {e}")
        df = pd.DataFrame()
        df["_source_table"] = table_name
    return df


def load_csv_to_database(engine) -> pd.DataFrame:
    """
    Load fraud_million_rows.csv into fraud_transactions table
    Returns DataFrame with the loaded data
    """
    logger.info(f"Loading CSV file: {CSV_PATH}")
    
    if not os.path.exists(CSV_PATH):
        logger.error(f"CSV file not found: {CSV_PATH}")
        return pd.DataFrame()
    
    try:
        # Load CSV
        df = pd.read_csv(CSV_PATH)
        logger.info(f"  → Loaded {len(df):,} rows from CSV")
        logger.info(f"  → Columns: {list(df.columns)}")
        
        # Convert boolean to integer (False=0, True=1)
        if 'is_fraudulent' in df.columns:
            df['is_fraudulent'] = df['is_fraudulent'].astype(int)
            fraud_count = df['is_fraudulent'].sum()
            logger.info(f"  → Fraud cases: {fraud_count} ({fraud_count/len(df)*100:.2f}%)")
        
        # Convert risk_score to float
        if 'risk_score' in df.columns:
            df['risk_score'] = pd.to_numeric(df['risk_score'], errors='coerce').fillna(0)
        
        # Add import timestamp
        df['imported_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Create table if not exists
        create_sql = """
        CREATE TABLE IF NOT EXISTS fraud_transactions (
            id INTEGER PRIMARY KEY,
            user_id TEXT,
            transaction_date TEXT,
            amount REAL,
            currency TEXT,
            exchange_rate REAL,
            converted_amount REAL,
            merchant TEXT,
            risk_score REAL,
            is_fraudulent INTEGER,
            hour_of_day INTEGER,
            day_of_week INTEGER,
            is_weekend INTEGER,
            imported_at TEXT,
            UNIQUE(id)
        )
        """
        with engine.begin() as conn:
            conn.execute(text(create_sql))
        
        # Check if already imported
        existing_count = 0
        try:
            existing = pd.read_sql("SELECT COUNT(*) as cnt FROM fraud_transactions", engine)
            existing_count = existing['cnt'].iloc[0] if not existing.empty else 0
            logger.info(f"  → Existing records in fraud_transactions: {existing_count:,}")
        except Exception:
            pass
        
        # Insert new records (avoid duplicates)
        if existing_count < len(df):
            df.to_sql('fraud_transactions', engine, if_exists='replace', index=False)
            logger.success(f"  → Loaded {len(df):,} rows into fraud_transactions table")
        else:
            logger.info(f"  → Data already exists in fraud_transactions")
        
        return df
        
    except Exception as e:
        logger.error(f"Error loading CSV: {e}")
        return pd.DataFrame()


def save_predictions(engine, df: pd.DataFrame) -> None:
    """Write prediction results back to fraud_predictions table."""
    logger.info(f"Writing {len(df):,} predictions to {OUTPUT_TABLE}")

    create_sql = f"""
    CREATE TABLE IF NOT EXISTS {OUTPUT_TABLE} (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        source_table        VARCHAR(100),
        source_id           BIGINT,
        symbol              VARCHAR(50),
        date                DATE,
        close               NUMERIC,
        volume              BIGINT,
        daily_return        NUMERIC,
        volatility_5d       NUMERIC,
        volume_surge        NUMERIC,
        rf_fraud_prob       NUMERIC,
        iso_anomaly_score   NUMERIC,
        ensemble_score      NUMERIC,
        predicted_fraud     BOOLEAN,
        predicted_reason    TEXT,
        model_version       VARCHAR(50),
        predicted_at        DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """
    with engine.begin() as conn:
        conn.execute(text(create_sql))

    # Prepare output
    output_cols = [
        "_source_table", "id", "symbol", "date", "close", "volume",
        "daily_return", "volatility_5d", "volume_surge",
        "rf_fraud_prob", "iso_anomaly_score", "ensemble_score",
        "predicted_fraud", "predicted_reason",
    ]
    
    # Filter to only existing columns
    output_cols = [c for c in output_cols if c in df.columns]
    
    out = df[output_cols].copy()
    
    # Rename columns for SQLite
    column_mapping = {
        "_source_table": "source_table",
        "id": "source_id",
        "predicted_fraud": "predicted_fraud",
    }
    out = out.rename(columns=column_mapping)
    
    out["model_version"] = "v1.0"
    out["predicted_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    out.to_sql(OUTPUT_TABLE, engine, if_exists="append", index=False)
    logger.success(f"Saved {len(out):,} predictions to {OUTPUT_TABLE}")


# ─────────────────────────────────────────────────────────────────────────────
# FEATURE ENGINEERING
# ─────────────────────────────────────────────────────────────────────────────

def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add engineered features derived from OHLCV + the pre-computed columns.
    All new columns are added in-place.
    """
    if df.empty:
        return df
    
    df = df.copy()

    # Sort for lag features
    if "symbol" in df.columns and "date" in df.columns:
        df = df.sort_values(["symbol", "date"]).reset_index(drop=True)

    eps = 1e-9   # avoid division by zero

    # Price structure features (only if columns exist)
    if all(c in df.columns for c in ["high", "low", "low"]):
        df["price_spread_pct"]  = (df["high"] - df["low"]) / (df["low"] + eps)
    
    if all(c in df.columns for c in ["close", "open"]):
        df["candle_body_pct"]   = np.abs(df["close"] - df["open"]) / (df["open"] + eps)
        df["close_vs_open"]     = df["close"] / (df["open"] + eps) - 1
    
    if all(c in df.columns for c in ["high", "close"]):
        df["high_close_ratio"]  = df["high"] / (df["close"] + eps)

    # Volume features
    if "volume" in df.columns:
        df["volume_log"]        = np.log1p(df["volume"].clip(lower=0))

    # Combined signals
    if "daily_return" in df.columns and "volume_surge" in df.columns:
        df["return_x_volume"]   = df["daily_return"].fillna(0) * df["volume_surge"].fillna(1)
        df["volatility_x_surge"] = df["volatility_5d"].fillna(0) * df["volume_surge"].fillna(1)

    # Gap detection (per symbol, requires previous day's close)
    if "symbol" in df.columns and "close" in df.columns and "open" in df.columns:
        df["prev_close"] = df.groupby("symbol")["close"].shift(1)
        df["gap_pct"]    = (df["open"] - df["prev_close"]) / (df["prev_close"] + eps)
        df["is_gap_up"]  = (df["gap_pct"] > 0.02).astype(int)
        df["is_gap_down"] = (df["gap_pct"] < -0.02).astype(int)
        df.drop(columns=["prev_close", "gap_pct"], inplace=True, errors="ignore")

    # Clip extreme outliers
    for col in ["price_spread_pct", "candle_body_pct", "return_x_volume"]:
        if col in df.columns:
            q_low = df[col].quantile(0.001)
            q_high = df[col].quantile(0.999)
            if not np.isnan(q_low) and not np.isnan(q_high):
                df[col] = df[col].clip(lower=q_low, upper=q_high)

    return df


def prepare_features(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """
    Select and clean feature matrix.
    Returns (X_df, feature_names).
    """
    if df.empty:
        return pd.DataFrame(), []
    
    available = [c for c in ALL_FEATURES if c in df.columns]
    missing   = [c for c in ALL_FEATURES if c not in df.columns]
    if missing:
        logger.warning(f"Missing features (will be skipped): {missing}")

    X = df[available].copy()

    # Fill NaN with median per column
    for col in X.columns:
        median_val = X[col].median()
        if not np.isnan(median_val):
            X[col] = X[col].fillna(median_val)
        else:
            X[col] = X[col].fillna(0)

    # Replace inf
    X = X.replace([np.inf, -np.inf], np.nan)
    X = X.fillna(0)

    return X, available


# ─────────────────────────────────────────────────────────────────────────────
# MODEL 1 — ISOLATION FOREST (unsupervised — works on all rows)
# ─────────────────────────────────────────────────────────────────────────────

def train_isolation_forest(X: pd.DataFrame) -> tuple[IsolationForest, np.ndarray]:
    """
    Train IsolationForest on the full dataset (no labels needed).
    Returns (model, anomaly_scores) where score > 0 = more anomalous.
    """
    if X.empty or len(X) < 10:
        logger.warning("Not enough data for IsolationForest")
        return None, np.zeros(len(X))
    
    logger.info(f"Training IsolationForest on {len(X):,} rows "
                f"(contamination={CONTAMINATION})")

    iso = IsolationForest(
        n_estimators   = 300,
        contamination  = CONTAMINATION,
        max_samples    = min(256, len(X)),
        random_state   = 42,
        n_jobs         = -1,
    )

    scaler  = RobustScaler()
    X_scaled = scaler.fit_transform(X)

    iso.fit(X_scaled)

    # decision_function: negative = more anomalous
    # Flip and normalise to [0, 1] — higher = more suspicious
    raw_scores     = iso.decision_function(X_scaled)
    norm_scores    = 1 - (raw_scores - raw_scores.min()) / (raw_scores.max() - raw_scores.min() + 1e-9)

    n_anomalies = (norm_scores > FRAUD_THRESHOLD).sum()
    logger.info(f"IsolationForest flagged {n_anomalies:,} anomalies "
                f"({n_anomalies/len(X)*100:.1f}%)")

    return iso, norm_scores


# ─────────────────────────────────────────────────────────────────────────────
# MODEL 2 — RANDOM FOREST CLASSIFIER (supervised — uses labeled rows)
# ─────────────────────────────────────────────────────────────────────────────

def train_random_forest(
    X_labeled: pd.DataFrame,
    y_labeled: pd.Series,
) -> tuple[Pipeline, np.ndarray, dict]:
    """
    Train RandomForestClassifier on labeled rows where is_suspicious is not null.
    Returns (pipeline, test_probabilities, metrics_dict).
    """
    if X_labeled.empty or len(X_labeled) < 5:
        logger.warning("Not enough labeled data for RandomForest")
        return None, {}
    
    logger.info(f"Training RandomForest on {len(X_labeled):,} labeled rows "
                f"({y_labeled.sum():,} fraud, {(~y_labeled).sum():,} clean)")

    # Handle class imbalance
    classes       = np.array([0, 1])
    class_weights = compute_class_weight("balanced", classes=classes, y=y_labeled.astype(int))
    weight_dict   = {0: class_weights[0], 1: class_weights[1]}
    logger.info(f"Class weights: {weight_dict}")

    # Build pipeline
    if HAS_IMBLEARN and y_labeled.sum() >= 5:
        pipe = ImbPipeline([
            ("scaler", RobustScaler()),
            ("smote",  SMOTE(random_state=42, k_neighbors=min(5, y_labeled.sum() - 1))),
            ("clf",    RandomForestClassifier(
                n_estimators      = 500,
                max_depth         = 12,
                min_samples_leaf  = 2,
                class_weight      = weight_dict,
                random_state      = 42,
                n_jobs            = -1,
            )),
        ])
    else:
        pipe = Pipeline([
            ("scaler", RobustScaler()),
            ("clf",    RandomForestClassifier(
                n_estimators      = 500,
                max_depth         = 12,
                min_samples_leaf  = 2,
                class_weight      = weight_dict,
                random_state      = 42,
                n_jobs            = -1,
            )),
        ])

    y_int = y_labeled.astype(int)
    metrics = {}

    # Need at least 2 samples per class to do a train/test split
    min_class_count = y_int.value_counts().min()

    if min_class_count >= 2 and len(X_labeled) >= 10:
        # Train / test split — stratified to keep fraud ratio
        X_train, X_test, y_train, y_test = train_test_split(
            X_labeled, y_int, test_size=0.2, stratify=y_int, random_state=42
        )
        pipe.fit(X_train, y_train)

        # Evaluate
        y_prob = pipe.predict_proba(X_test)[:, 1]
        y_pred = (y_prob >= FRAUD_THRESHOLD).astype(int)

        if y_test.sum() > 0:
            metrics["roc_auc"]   = roc_auc_score(y_test, y_prob)
            metrics["avg_prec"]  = average_precision_score(y_test, y_prob)
            metrics["report"]    = classification_report(y_test, y_pred, digits=4)
            metrics["confusion"] = confusion_matrix(y_test, y_pred)

            logger.info(f"\nClassification Report:\n{metrics['report']}")
            logger.info(f"ROC-AUC:  {metrics['roc_auc']:.4f}")
            logger.info(f"Avg Prec: {metrics['avg_prec']:.4f}")

        # Cross-validation
        if len(X_labeled) >= 50:
            cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
            cv_scores = cross_val_score(pipe, X_labeled, y_int, cv=cv,
                                        scoring="roc_auc", n_jobs=-1)
            metrics["cv_roc_auc"] = cv_scores
            logger.info(f"CV ROC-AUC: {cv_scores.mean():.4f} ± {cv_scores.std():.4f}")
    else:
        # Too few samples — train on all labeled data, skip eval
        logger.warning(
            f"Only {len(X_labeled)} labeled rows with min class count {min_class_count} "
            "— training on full labeled set, skipping eval split"
        )
        pipe.fit(X_labeled, y_int)

    return pipe, metrics


def predict_all_random_forest(
    pipe: Pipeline,
    X_all: pd.DataFrame,
) -> np.ndarray:
    """Run the trained RF on the full dataset (labeled + unlabeled)."""
    if pipe is None or X_all.empty:
        return np.full(len(X_all), 0.5)
    probs = pipe.predict_proba(X_all)[:, 1]
    return probs


# ─────────────────────────────────────────────────────────────────────────────
# ENSEMBLE SCORING
# ─────────────────────────────────────────────────────────────────────────────

def ensemble_score(
    rf_probs:   np.ndarray,
    iso_scores: np.ndarray,
    rf_weight:  float = 0.65,
    iso_weight: float = 0.35,
) -> np.ndarray:
    """
    Weighted average of supervised RF probability and unsupervised ISO score.
    RF gets higher weight when we have enough labeled data (>100 rows).
    Falls back to ISO-only when RF is unavailable.
    """
    return rf_weight * rf_probs + iso_weight * iso_scores


# ─────────────────────────────────────────────────────────────────────────────
# SUSPICION REASON GENERATOR
# ─────────────────────────────────────────────────────────────────────────────

def generate_reason(row: pd.Series) -> str:
    """
    Generate a human-readable suspicion reason from the feature values.
    Mirrors the format of the existing suspicion_reason column.
    """
    reasons = []

    daily_return = row.get("daily_return", 0) or 0
    volatility   = row.get("volatility_5d", 0) or 0
    vol_surge    = row.get("volume_surge", 1) or 1
    spread       = row.get("price_spread_pct", 0) or 0
    candle       = row.get("candle_body_pct", 0) or 0
    is_gap_up    = row.get("is_gap_up", 0)
    is_gap_down  = row.get("is_gap_down", 0)

    if abs(daily_return) > 0.10:
        direction = "spike" if daily_return > 0 else "drop"
        reasons.append(f"extreme price {direction} ({daily_return*100:.1f}%)")

    if volatility > 0.05:
        reasons.append(f"high 5-day volatility ({volatility*100:.1f}%)")

    if vol_surge > 5.0:
        reasons.append(f"volume surge {vol_surge:.1f}x average")

    if spread > 0.10:
        reasons.append(f"wide price spread ({spread*100:.1f}%)")

    if candle > 0.08:
        reasons.append(f"large candle body ({candle*100:.1f}%)")

    if is_gap_up:
        reasons.append("gap-up open >2%")

    if is_gap_down:
        reasons.append("gap-down open >2%")

    if not reasons:
        reasons.append("anomaly pattern detected by ensemble model")

    return "; ".join(reasons)


# ─────────────────────────────────────────────────────────────────────────────
# FEATURE IMPORTANCE
# ─────────────────────────────────────────────────────────────────────────────

def print_feature_importance(pipe: Pipeline, feature_names: list[str]) -> None:
    if pipe is None:
        return
    clf = pipe.named_steps["clf"]
    if not hasattr(clf, "feature_importances_"):
        return

    importances = clf.feature_importances_
    idx         = np.argsort(importances)[::-1]

    print("\n─── Feature Importance (RandomForest) ───────────────────────")
    for rank, i in enumerate(idx[:15], 1):
        if i < len(feature_names):
            bar = "█" * int(importances[i] * 80)
            print(f"  {rank:2d}. {feature_names[i]:<30s} {importances[i]:.4f}  {bar}")
    print()


# ─────────────────────────────────────────────────────────────────────────────
# MAIN PIPELINE
# ─────────────────────────────────────────────────────────────────────────────

def run_fraud_detection() -> pd.DataFrame:
    engine = get_engine()

    # ── 0. Load CSV into database (NEW ADDITION) ─────────────────────────────
    logger.info("=" * 60)
    logger.info("STEP 0: Loading CSV into database")
    logger.info("=" * 60)
    csv_df = load_csv_to_database(engine)
    
    # ── 1. Load both tables ──────────────────────────────────────────────────
    logger.info("=" * 60)
    logger.info("STEP 1: Loading tables from database")
    logger.info("=" * 60)
    df_hist = load_table(engine, "clean_historical_prices")
    df_rt   = load_table(engine, "clean_realtime_quotes")

    df = pd.concat([df_hist, df_rt], ignore_index=True)
    logger.info(f"Combined dataset: {len(df):,} rows from both tables")

    # Show CSV summary if loaded
    if not csv_df.empty:
        logger.info(f"\nCSV fraud_transactions summary:")
        logger.info(f"  Total transactions: {len(csv_df):,}")
        if 'is_fraudulent' in csv_df.columns:
            logger.info(f"  Fraudulent: {csv_df['is_fraudulent'].sum():,}")
            logger.info(f"  Non-fraudulent: {(csv_df['is_fraudulent'] == 0).sum():,}")

    # Coerce types
    if not df.empty:
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"], errors='coerce')
        if LABEL_COL in df.columns:
            df[LABEL_COL] = df[LABEL_COL].astype("boolean")

        numeric_cols = ["open", "high", "low", "close", "volume",
                        "daily_return", "volatility_5d", "volume_surge"]
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

    # ── 2. Feature engineering ───────────────────────────────────────────────
    logger.info("=" * 60)
    logger.info("STEP 2: Engineering features")
    logger.info("=" * 60)
    df = engineer_features(df)
    X_all, feature_names = prepare_features(df)
    logger.info(f"Feature matrix: {X_all.shape[0]:,} rows × {X_all.shape[1]} features")

    if X_all.empty:
        logger.error("No features available. Exiting.")
        return pd.DataFrame()

    # ── 3. Isolation Forest (all rows) ───────────────────────────────────────
    logger.info("=" * 60)
    logger.info("STEP 3: Training Isolation Forest")
    logger.info("=" * 60)
    _, iso_scores = train_isolation_forest(X_all)

    # ── 4. Random Forest (labeled rows only) ─────────────────────────────────
    labeled_mask = df[LABEL_COL].notna() if LABEL_COL in df.columns else pd.Series([False] * len(df))
    n_labeled    = labeled_mask.sum()
    logger.info(f"Labeled rows: {n_labeled:,} / {len(df):,} total")

    rf_probs = np.full(len(df), 0.5)   # default when no RF available
    rf_pipe = None

    if n_labeled >= 20:
        X_labeled = X_all[labeled_mask]
        y_labeled = df.loc[labeled_mask, LABEL_COL].astype(bool)

        rf_pipe, metrics = train_random_forest(X_labeled, y_labeled)
        if rf_pipe is not None:
            rf_probs = predict_all_random_forest(rf_pipe, X_all)
            print_feature_importance(rf_pipe, feature_names)

            # Adjust weights if very few labels
            rf_weight  = 0.65 if n_labeled >= 100 else 0.45
            iso_weight = 1 - rf_weight
            logger.info(f"Ensemble weights: RF={rf_weight}, ISO={iso_weight}")
        else:
            rf_weight, iso_weight = 0.0, 1.0
    else:
        logger.warning(f"Only {n_labeled} labeled rows — using IsolationForest only (ISO weight=1.0)")
        rf_weight, iso_weight = 0.0, 1.0

    # ── 5. Ensemble ──────────────────────────────────────────────────────────
    logger.info("=" * 60)
    logger.info("STEP 4: Computing ensemble scores")
    logger.info("=" * 60)
    scores = ensemble_score(rf_probs, iso_scores, rf_weight, iso_weight)

    df["rf_fraud_prob"]      = rf_probs
    df["iso_anomaly_score"]  = iso_scores
    df["ensemble_score"]     = scores
    df["predicted_fraud"]    = scores >= FRAUD_THRESHOLD

    # ── 6. Generate reasons ──────────────────────────────────────────────────
    logger.info("STEP 5: Generating suspicion reasons")
    fraud_idx = df[df["predicted_fraud"]].index
    df["predicted_reason"] = ""
    if len(fraud_idx) > 0:
        df.loc[fraud_idx, "predicted_reason"] = (
            df.loc[fraud_idx].apply(generate_reason, axis=1)
        )

    # ── 7. Summary ───────────────────────────────────────────────────────────
    total_flagged   = df["predicted_fraud"].sum()
    hist_flagged    = df[df["_source_table"] == "clean_historical_price"]["predicted_fraud"].sum() if not df_hist.empty else 0
    rt_flagged      = df[df["_source_table"] == "clean_realtime_quotes"]["predicted_fraud"].sum() if not df_rt.empty else 0

    print("\n" + "═"*60)
    print("  FRAUD DETECTION RESULTS")
    print("═"*60)
    print(f"  Total rows analysed  : {len(df):,}")
    print(f"  Historical flagged   : {hist_flagged:,} / {len(df_hist):,} "
          f"({hist_flagged/max(len(df_hist),1)*100:.2f}%)")
    print(f"  Realtime flagged     : {rt_flagged:,} / {len(df_rt):,} "
          f"({rt_flagged/max(len(df_rt),1)*100:.2f}%)")
    print(f"  Total fraud flags    : {total_flagged:,} "
          f"({total_flagged/len(df)*100:.2f}%)")
    print(f"  Fraud threshold      : {FRAUD_THRESHOLD}")
    print("═"*60 + "\n")

    # Top 20 most suspicious
    if not df.empty and df["predicted_fraud"].any():
        top20 = (
            df[df["predicted_fraud"]]
            .sort_values("ensemble_score", ascending=False)
            .head(20)
        )
        display_cols = [c for c in ["symbol", "date", "close", "daily_return", "volume_surge",
                      "ensemble_score", "predicted_reason", "_source_table"] if c in top20.columns]
        if display_cols:
            print("  TOP 20 MOST SUSPICIOUS RECORDS:")
            print(top20[display_cols].to_string(index=False))
            print()

    # ── 8. Compare with existing labels ──────────────────────────────────────
    if n_labeled >= 10 and LABEL_COL in df.columns:
        labeled_df  = df[labeled_mask].copy()
        true_labels = labeled_df[LABEL_COL].astype(bool)
        pred_labels = labeled_df["predicted_fraud"]

        print("  COMPARISON WITH EXISTING is_suspicious LABELS:")
        print(f"  Agreement rate: "
              f"{(true_labels == pred_labels).mean()*100:.1f}%")

        existing_fraud = true_labels.sum()
        model_fraud    = pred_labels.sum()
        print(f"  Existing labels say fraud : {existing_fraud:,}")
        print(f"  Model predicts fraud      : {model_fraud:,}")

        new_detections = ((pred_labels) & (~true_labels)).sum()
        missed         = ((~pred_labels) & (true_labels)).sum()
        print(f"  New detections (not in labels) : {new_detections:,}")
        print(f"  Missed (in labels, not caught) : {missed:,}")
        print()

    # ── 9. Save predictions ───────────────────────────────────────────────────
    logger.info("=" * 60)
    logger.info("STEP 6: Saving predictions to database")
    logger.info("=" * 60)
    save_predictions(engine, df)

    return df


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logger.info("Starting fraud detection pipeline")
    results = run_fraud_detection()
    logger.success("Pipeline complete")
    
    # Show final summary
    print("\n" + "═"*60)
    print("  DATABASE SUMMARY")
    print("═"*60)
    print(f"  Database location: {DB_PATH}")
    print(f"  Tables available: clean_historical_price, clean_realtime_quotes, fraud_transactions, fraud_predictions")
    print("═"*60)