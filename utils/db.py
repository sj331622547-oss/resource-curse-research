import os
import datetime
import pandas as pd
from sqlalchemy import create_engine, inspect, text


def get_engine():
    """SQLite locally; PostgreSQL on Streamlit Cloud via secrets."""
    try:
        import streamlit as st
        url = st.secrets["database"]["url"]
        if url:
            return create_engine(url, pool_pre_ping=True)
    except Exception:
        pass
    os.makedirs("data", exist_ok=True)
    return create_engine("sqlite:///data/research.db")


def save_data(df: pd.DataFrame, table: str, if_exists: str = "replace"):
    engine = get_engine()
    df.to_sql(table, engine, if_exists=if_exists, index=False)


def load_data(table: str) -> pd.DataFrame:
    engine = get_engine()
    try:
        with engine.connect() as conn:
            return pd.read_sql(f'SELECT * FROM "{table}"', conn)
    except Exception:
        return pd.DataFrame()


def table_exists(table: str) -> bool:
    return inspect(get_engine()).has_table(table)


def get_db_summary() -> dict:
    """Return row counts for all tables."""
    engine = get_engine()
    insp = inspect(engine)
    summary = {}
    for t in insp.get_table_names():
        try:
            with engine.connect() as conn:
                n = pd.read_sql(f'SELECT COUNT(*) AS n FROM "{t}"', conn).iloc[0, 0]
            summary[t] = int(n)
        except Exception:
            summary[t] = 0
    return summary


def log_collection(source: str, status: str, rows: int, message: str = ""):
    df = pd.DataFrame([{
        "timestamp": datetime.datetime.now().isoformat(),
        "source": source,
        "status": status,
        "rows_collected": int(rows),
        "message": message,
    }])
    save_data(df, "collection_log", if_exists="append")


def get_collection_log() -> pd.DataFrame:
    return load_data("collection_log")
