import json, logging, sqlite3, random
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
import numpy as np
import requests

# CONFIGURATION
API_KEY = "abcdefghijklmnopqrstuvwxyz123456"
URL = "https://api.bnm.gov.my/public/exchange-rate"
DB_NAME = "fraud_million.db"
CSV_FILE = "fraud_million_rows.csv"
NUM_ROWS = 1_000_000  # 1 million rows

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class FraudDataGenerator:
    def __init__(self, num_rows: int = 1000000):
        self.num_rows = num_rows
        self.users = [f"user_{i:05d}" for i in range(1, 1001)]  # 1000 users
        self.merchants = ["Amazon","Walmart","Target","Best Buy","Apple","Starbucks","Netflix",
                         "Uber","Airbnb","Unknown Merchant","Wire Transfer","Crypto Exchange",
                         "Western Union","PayPal","Venmo","eBay","Shopify","Google","Microsoft"]
        self.currencies = ["USD","EUR","GBP","JPY","CAD","AUD","CHF","CNY","SGD","MYR"]
        self.exchange_rates = {"USD":1.0,"EUR":1.08,"GBP":1.25,"JPY":0.0067,"CAD":0.74,
                               "AUD":0.66,"CHF":1.12,"CNY":0.14,"SGD":0.74,"MYR":0.21}
        
    def fetch_real_exchange_rates(self):
        """Fetch real exchange rates from API"""
        try:
            headers = {'Accept': 'application/vnd.BNM.API.v1+json', 'X-API-Key': API_KEY}
            response = requests.get(URL, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if 'data' in data:
                    for item in data['data']:
                        if 'currency' in item and 'rate' in item:
                            self.exchange_rates[item['currency']] = float(item['rate'])
                    logger.info(f"Fetched real exchange rates from API")
        except Exception as e:
            logger.warning(f"Using default exchange rates: {e}")
    
    def generate_transaction(self, transaction_id: int, date: datetime):
        """Generate single transaction with fraud patterns"""
        user = random.choice(self.users)
        merchant = random.choice(self.merchants)
        
        # Amount generation with fraud patterns
        rand = random.random()
        if rand < 0.03:  # 3% high-value fraud
            amount = random.uniform(50000, 500000)
            is_fraudulent = True
            risk_score = random.uniform(0.85, 0.99)
        elif rand < 0.08:  # 5% medium-risk
            amount = random.uniform(10000, 50000)
            is_fraudulent = random.random() < 0.7
            risk_score = random.uniform(0.6, 0.9)
        elif merchant in ["Unknown Merchant", "Wire Transfer", "Crypto Exchange"]:
            amount = random.uniform(5000, 100000)
            is_fraudulent = random.random() < 0.5
            risk_score = random.uniform(0.5, 0.85)
        else:
            amount = random.uniform(5, 500)
            is_fraudulent = False
            risk_score = random.uniform(0.01, 0.3)
        
        # Weekend fraud boost
        if date.weekday() >= 5 and is_fraudulent:
            risk_score = min(risk_score * 1.2, 1.0)
        
        currency = random.choice(self.currencies)
        exchange_rate = self.exchange_rates.get(currency, 1.0)
        
        return {
            'id': transaction_id,
            'user_id': user,
            'transaction_date': date.strftime('%Y-%m-%d %H:%M:%S'),
            'amount': round(amount, 2),
            'currency': currency,
            'exchange_rate': exchange_rate,
            'converted_amount': round(amount * exchange_rate, 2),
            'merchant': merchant,
            'risk_score': round(risk_score, 3),
            'is_fraudulent': is_fraudulent,
            'hour_of_day': date.hour,
            'day_of_week': date.weekday(),
            'is_weekend': date.weekday() >= 5
        }
    
    def generate_million_rows(self):
        """Generate 1 million transaction rows"""
        logger.info(f"Generating {self.num_rows:,} transactions...")
        
        # Fetch real exchange rates
        self.fetch_real_exchange_rates()
        
        transactions = []
        start_date = datetime(2024, 1, 1)
        batch_size = 50000
        
        for i in range(1, self.num_rows + 1):
            # Spread transactions across 2024-2025
            days_offset = random.randint(0, 730)
            hours_offset = random.randint(0, 23)
            transaction_date = start_date + timedelta(days=days_offset, hours=hours_offset)
            
            transaction = self.generate_transaction(i, transaction_date)
            transactions.append(transaction)
            
            # Progress tracking and batch saving
            if i % batch_size == 0:
                logger.info(f"Generated {i:,}/{self.num_rows:,} rows ({i/self.num_rows*100:.1f}%)")
                # Save intermediate batch to CSV
                temp_df = pd.DataFrame(transactions[-batch_size:])
                mode = 'a' if i > batch_size else 'w'
                header = (i == batch_size)
                temp_df.to_csv(CSV_FILE, mode=mode, header=header, index=False)
        
        df = pd.DataFrame(transactions)
        logger.info(f"Generated {len(df):,} transactions with {df['is_fraudulent'].sum():,} fraud cases")
        return df

def add_fraud_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add fraud detection features"""
    logger.info("Adding fraud detection features...")
    
    # Statistical features
    df['amount_zscore'] = (df['amount'] - df['amount'].mean()) / df['amount'].std()
    df['is_zscore_anomaly'] = df['amount_zscore'].abs() > 3
    
    # User-based features
    user_stats = df.groupby('user_id')['amount'].agg(['mean', 'std']).rename(
        columns={'mean': 'user_avg_amount', 'std': 'user_std_amount'})
    df = df.merge(user_stats, on='user_id', how='left')
    df['user_deviation'] = (df['amount'] - df['user_avg_amount']) / df['user_std_amount'].replace(0, 1)
    
    # Merchant risk
    merchant_fraud_rate = df.groupby('merchant')['is_fraudulent'].mean().to_dict()
    df['merchant_fraud_rate'] = df['merchant'].map(merchant_fraud_rate)
    
    # Combined fraud score
    df['fraud_score'] = (
        df['risk_score'] * 0.4 +
        df['is_zscore_anomaly'].astype(int) * 0.3 +
        (df['user_deviation'] > 3).astype(int) * 0.3
    )
    df['final_prediction'] = df['fraud_score'] > 0.5
    
    return df

def save_to_sqlite(df: pd.DataFrame, db_name: str):
    """Save to SQLite with indexing"""
    logger.info(f"Saving {len(df):,} rows to SQLite...")
    with sqlite3.connect(db_name) as conn:
        df.to_sql('transactions', conn, if_exists='replace', index=False)
        cursor = conn.cursor()
        cursor.execute("CREATE INDEX idx_fraud ON transactions(is_fraudulent)")
        cursor.execute("CREATE INDEX idx_user ON transactions(user_id)")
        cursor.execute("CREATE INDEX idx_date ON transactions(transaction_date)")
        count = cursor.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
        logger.info(f"Saved {count:,} records to {db_name}")

def generate_report(df: pd.DataFrame):
    """Print fraud analysis report"""
    print("\n" + "="*60)
    print("FRAUD DETECTION REPORT - 1 MILLION TRANSACTIONS")
    print("="*60)
    print(f"\n📊 TOTAL TRANSACTIONS: {len(df):,}")
    print(f"🚨 FRAUDULENT CASES: {df['is_fraudulent'].sum():,}")
    print(f"📈 FRAUD RATE: {df['is_fraudulent'].sum()/len(df)*100:.2f}%")
    print(f"💰 TOTAL AMOUNT: ${df['amount'].sum():,.2f}")
    print(f"💸 FRAUD AMOUNT: ${df[df['is_fraudulent']]['amount'].sum():,.2f}")
    
    print(f"\n🏪 TOP 5 FRAUDULENT MERCHANTS:")
    fraud_merchants = df[df['is_fraudulent']]['merchant'].value_counts().head(5)
    for merchant, count in fraud_merchants.items():
        print(f"   {merchant}: {count:,} frauds")
    
    print(f"\n👥 TOP 5 HIGH-RISK USERS:")
    user_fraud = df.groupby('user_id')['is_fraudulent'].sum().sort_values(ascending=False).head(5)
    for user, count in user_fraud.items():
        print(f"   {user}: {count} frauds")
    
    print(f"\n⏰ FRAUD BY HOUR:")
    hour_fraud = df[df['is_fraudulent']]['hour_of_day'].value_counts().sort_index().head(6)
    for hour, count in hour_fraud.items():
        print(f"   {hour:02d}:00 - {count} frauds")
    
    print("\n" + "="*60)

def main():
    """Main execution"""
    print("\n🚀 STARTING 1 MILLION ROW FRAUD DETECTION SYSTEM")
    print(f"🎯 Target: {NUM_ROWS:,} transactions")
    
    # Generate data
    generator = FraudDataGenerator(NUM_ROWS)
    df = generator.generate_million_rows()
    
    # Add fraud detection features
    df = add_fraud_features(df)
    
    # Save to SQLite
    save_to_sqlite(df, DB_NAME)
    
    # Generate report
    generate_report(df)
    
    # Show sample
    print("\n📋 SAMPLE DATA (First 10 rows):")
    print(df[['id', 'user_id', 'amount', 'merchant', 'risk_score', 'is_fraudulent']].head(10).to_string(index=False))
    
    # File info
    csv_size = Path(CSV_FILE).stat().st_size / (1024*1024)
    db_size = Path(DB_NAME).stat().st_size / (1024*1024)
    print(f"\n📁 Files Created:")
    print(f"   • {CSV_FILE}: {csv_size:.1f} MB")
    print(f"   • {DB_NAME}: {db_size:.1f} MB")
    print(f"\n✅ COMPLETE! {NUM_ROWS:,} rows analyzed for fraud detection")

if __name__ == "__main__":
    main()