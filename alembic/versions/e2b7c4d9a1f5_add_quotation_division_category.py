"""add quotation division and category

Revision ID: e2b7c4d9a1f5
Revises: d8a4f1c6e9b3
Create Date: 2026-10-10 20:20:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e2b7c4d9a1f5'
down_revision = 'd8a4f1c6e9b3'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('quotations', sa.Column('division', sa.String(length=20), nullable=True))
    op.add_column('quotations', sa.Column('category', sa.String(length=20), nullable=True))
    op.create_index('ix_quotations_division', 'quotations', ['division'])
    op.create_index('ix_quotations_category', 'quotations', ['category'])

    # Existing quotations take their project's division and category, and
    # failing that their customer's category. Nothing else is changed.
    op.execute("""
        UPDATE quotations SET division =
            (SELECT p.division FROM projects p WHERE p.id = quotations.project_id)
        WHERE division IS NULL AND project_id IS NOT NULL
    """)
    op.execute("""
        UPDATE quotations SET category =
            (SELECT p.category FROM projects p WHERE p.id = quotations.project_id)
        WHERE category IS NULL AND project_id IS NOT NULL
    """)
    op.execute("""
        UPDATE quotations SET category =
            (SELECT c.category FROM customers c WHERE c.id = quotations.customer_id)
        WHERE category IS NULL
    """)


def downgrade():
    op.drop_index('ix_quotations_category', table_name='quotations')
    op.drop_index('ix_quotations_division', table_name='quotations')
    op.drop_column('quotations', 'category')
    op.drop_column('quotations', 'division')
