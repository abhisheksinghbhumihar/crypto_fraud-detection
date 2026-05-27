# fraud_detection_api/app/core/database.py
import sqlite3
from pathlib import Path
from app.core.config import settings

def get_db_connection():
    """Get SQLite database connection"""
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    return conn

def create_api_tables():
    """Create database tables for the API"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Create transactions table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_id TEXT UNIQUE,
            user_id TEXT,
            merchant_id TEXT,
            amount REAL,
            risk_score REAL,
            is_fraud INTEGER,
            decision TEXT,
            timestamp TEXT,
            evidence_hash TEXT
        )
    ''')
    
    # Create evidence table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS evidence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            evidence_hash TEXT UNIQUE,
            transaction_id TEXT,
            data TEXT,
            timestamp TEXT
        )
    ''')
    
    conn.commit()
    conn.close()

def check_database_connection() -> bool:
    """Check if database is accessible"""
    try:
        conn = get_db_connection()
        conn.close()
        return True
    except Exception:
        return False

def get_all_tables_info() -> dict:
    """Get all tables and their data"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    tables = {}
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    table_names = [row[0] for row in cursor.fetchall()]
    
    for table_name in table_names:
        cursor.execute(f"SELECT * FROM {table_name} LIMIT 100")
        rows = cursor.fetchall()
        tables[table_name] = [dict(row) for row in rows]
    
    conn.close()
    return tables