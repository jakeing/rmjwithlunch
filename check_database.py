"""
Check what's in the database
"""
import sqlite3

DB_PATH = 'workorders.db'

def check_database():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Get all tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        
        print("="*60)
        print("TABLES IN DATABASE:")
        print("="*60)
        if tables:
            for table in tables:
                print(f"\n📋 Table: {table[0]}")
                cursor.execute(f"PRAGMA table_info({table[0]})")
                columns = cursor.fetchall()
                for col in columns:
                    print(f"  - {col[1]} ({col[2]})")
        else:
            print("⚠️  NO TABLES FOUND IN DATABASE!")
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    check_database()