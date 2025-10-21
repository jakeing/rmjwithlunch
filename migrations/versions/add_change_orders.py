"""Add change orders

Revision ID: add_change_orders_v2
Revises: 1ca9b907a5a8
Create Date: 2024-01-15 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_change_orders_v2'
down_revision = '1ca9b907a5a8'
branch_labels = None
depends_on = None


def upgrade():
    # Create change_order table
    op.create_table('change_order',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('work_order_id', sa.Integer(), nullable=False),
        sa.Column('change_order_number', sa.String(length=50), nullable=False),
        sa.Column('description', sa.String(length=200), nullable=False),
        sa.Column('estimated_hours', sa.Float(), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=True),
        sa.Column('created_date', sa.Date(), nullable=True),
        sa.Column('approved_date', sa.Date(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['work_order_id'], ['work_order.id'], name='fk_change_order_work_order'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Add change_order_id column to time_entry table
    with op.batch_alter_table('time_entry', schema=None) as batch_op:
        batch_op.add_column(sa.Column('change_order_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_time_entry_change_order', 'change_order', ['change_order_id'], ['id'])


def downgrade():
    # Remove foreign key and column from time_entry
    with op.batch_alter_table('time_entry', schema=None) as batch_op:
        batch_op.drop_constraint('fk_time_entry_change_order', type_='foreignkey')
        batch_op.drop_column('change_order_id')
    
    # Drop change_order table
    op.drop_table('change_order')