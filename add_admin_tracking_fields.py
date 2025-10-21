"""
Add comprehensive tracking fields for admin work order management
"""
import sqlite3

DB_PATH = 'instance/workorders.db'

def add_tracking_fields():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # List of new columns to add
    new_columns = [
        ('wo_received_date', 'DATE'),
        ('work_released', 'BOOLEAN DEFAULT 0'),
        ('estimate_needed', 'BOOLEAN DEFAULT 0'),
        ('estimate_amount', 'FLOAT'),
        ('estimate_submitted_date', 'DATE'),
        ('estimate_approved', 'BOOLEAN DEFAULT 0'),
        ('pur_received_date', 'DATE'),
        ('pur_number', 'VARCHAR(50)'),
        ('report_needed', 'BOOLEAN DEFAULT 0'),
        ('report_review_by_beverly', 'VARCHAR(50)'),
        ('report_review_needed', 'BOOLEAN DEFAULT 0'),
        ('report_approved_date', 'DATE'),
        ('completion_notice_email_date', 'DATE'),
        ('ready_to_bill', 'BOOLEAN DEFAULT 0'),
        ('check_for_ot', 'BOOLEAN DEFAULT 0'),
        ('time_adjustments', 'TEXT'),
        ('change_order_date', 'DATE'),
        ('co_submitted_date', 'DATE'),
        ('co_approval_received_date', 'DATE'),
        ('notes', 'TEXT'),
    ]
    
    try:
        print("Adding tracking fields to work_order table...")
        
        for column_name, column_type in new_columns:
            try:
                cursor.execute(f'ALTER TABLE work_order ADD COLUMN {column_name} {column_type}')
                print(f"✓ Added {column_name}")
            except sqlite3.OperationalError as e:
                if "duplicate column" in str(e).lower():
                    print(f"  - {column_name} already exists")
                else:
                    raise
        
        conn.commit()
        print("\n" + "="*60)
        print("✓ All tracking fields added successfully!")
        print("="*60)
        
    except Exception as e:
        conn.rollback()
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        conn.close()

if __name__ == "__main__":
    print("="*60)
    print("Add Admin Tracking Fields")
    print("="*60)
    print("\nThis will add comprehensive tracking fields to work orders")
    print("for complete lifecycle management.\n")
    
    response = input("Proceed? (yes/no): ")
    
    if response.lower() in ['yes', 'y']:
        add_tracking_fields()
    else:
        print("Cancelled.")