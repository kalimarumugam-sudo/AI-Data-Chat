import os

import pandas as pd
import streamlit as st

CSV_FILE = "data/csv/sample_rates.csv"


@st.cache_data
def load_rates_data():
    """Load sample rate analysis data from CSV file."""
    try:
        if os.path.exists(CSV_FILE):
            df = pd.read_csv(CSV_FILE, sep=";", engine="python")
            return df, None
        return None, f"CSV file '{CSV_FILE}' not found."
    except Exception as e:
        return None, f"Error loading CSV file: {str(e)}"


@st.cache_data
def load_data():
    """Main data loading function."""
    df, error = load_rates_data()
    if df is not None:
        return df, f"Loaded data from '{CSV_FILE}' ({len(df)} rows)", None
    return None, None, error


def get_data_summary(df):
    """Get summary information about the loaded data."""
    return {
        "rows": len(df),
        "columns": list(df.columns),
        "data_types": df.dtypes.to_dict(),
        "missing_values": df.isnull().sum().to_dict(),
    }
