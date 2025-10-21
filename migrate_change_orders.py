"""
Manual migration script to add change order support
Run this with: python migrate_change_orders.py
"""
import sqlite3
from datetime import datetime

# Path to your database
DB_PATH = 'workorders.db'

def migrate_database():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        print("Starting migration...")
        
        # 1. Create ChangeOrder table
        print("Creating change_order table...")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS change_order (
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
        
        # 2. Add change_order_id column to time_entry table
        print("\nAdding change_order_id column to time_entry table...")
        try:
            cursor.execute('''
                ALTER TABLE time_entry 
                ADD COLUMN change_order_id INTEGER
            ''')
            print("✓ Added change_order_id column")
        except sqlite3.OperationalError as e:
            if "duplicate column" in str(e).lower():
                print("✓ change_order_id column already exists")
            else:
                raise
        
        # 3. Update the alembic_version table to mark this migration as done
        print("\nUpdating migration version...")
        cursor.execute('''
            UPDATE alembic_version 
            SET version_num = 'add_change_orders_v2'
        ''')
        
        # Commit the changes
        conn.commit()
        print("\n" + "="*60)
        print("✓ Migration completed successfully!")
        print("="*60)
        print("\nYou can now:")
        print("  1. Restart your Flask application")
        print("  2. Create change orders for work orders")
        print("  3. Log time to change orders")
        
    except Exception as e:
        conn.rollback()
        print(f"\n✗ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    print("=" * 60)
    print("Change Order Migration Script")
    print("=" * 60)
    print(f"\nDatabase: {DB_PATH}")
    print("\nThis will:")
    print("  1. Create the change_order table")
    print("  2. Add change_order_id column to time_entry table")
    print("  3. Update the migration version")
    
    response = input("\nProceed with migration? (yes/no): ")
    
    if response.lower() in ['yes', 'y']:
        migrate_database()
    else:
        print("Migration cancelled.")