"""
Direct database fix - adds change_order_id column
"""
import sqlite3

DB_PATH = 'instance/workorders.db'

def fix_database():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        print("Checking database structure...")
        
        # Check current columns in time_entry
        cursor.execute("PRAGMA table_info(time_entry)")
        columns = cursor.fetchall()
        column_names = [col[1] for col in columns]
        
        print(f"\nCurrent time_entry columns: {column_names}")
        
        if 'change_order_id' in column_names:
            print("\n✓ change_order_id column already exists!")
        else:
            print("\n Adding change_order_id column...")
            cursor.execute('ALTER TABLE time_entry ADD COLUMN change_order_id INTEGER')
            print("✓ Added change_order_id column")
        
        # Check if change_order table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='change_order'")
        if cursor.fetchone():
            print("✓ change_order table already exists")
        else:
            print("\nCreating change_order table...")
            cursor.execute('''
                CREATE TABLE change_order (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    work_order_id INTEGER NOT NULL,
                    change_order_number VARCHAR(50) NOT NULL,
                    description VARCHAR(200) NOT NULL,
                    estimated_hours FLOAT DEFAULT 0,
                    status VARCHAR(50) DEFAULT 'Open',
                    created_date DATE,
                    approved_date DATE,
                    notes TEXT,
                    FOREIGN KEY(work_order_id) REFERENCES work_order(id)
                )
            ''')
            print("✓ Created change_order table")
        
        conn.commit()
        print("\n" + "="*60)
        print("✓ Database fixed successfully!")
        print("="*60)
        print("\nYou can now restart your Flask application.")
        
    except Exception as e:
        conn.rollback()
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        conn.close()

if __name__ == "__main__":
    print("="*60)
    print("Database Fix Script")
    print("="*60)
    print("\nThis will add the change_order_id column to time_entry")
    print("and create the change_order table if needed.\n")
    
    fix_database()