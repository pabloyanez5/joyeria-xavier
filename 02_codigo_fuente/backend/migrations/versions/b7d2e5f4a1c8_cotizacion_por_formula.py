"""cotizacion por formula (peso x precio por gramo + mano de obra)

Revision ID: b7d2e5f4a1c8
Revises: a3f1c9d27b40
Create Date: 2026-11-10 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7d2e5f4a1c8'
down_revision: Union[str, Sequence[str], None] = 'a3f1c9d27b40'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('productos', sa.Column('peso_gramos', sa.Numeric(7, 2), nullable=True))
    op.add_column('productos', sa.Column('mano_obra', sa.Numeric(10, 2), nullable=True))
    op.add_column('productos', sa.Column('imagen_url', sa.String(500), nullable=True))
    op.create_table(
        'tarifas_material',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('material', sa.String(50), nullable=False),
        sa.Column('quilataje', sa.String(10), nullable=True),
        sa.Column('precio_gramo', sa.Numeric(10, 2), nullable=False),
        sa.Column('vigente_desde', sa.Date(), nullable=False),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('tarifas_material')
    op.drop_column('productos', 'imagen_url')
    op.drop_column('productos', 'mano_obra')
    op.drop_column('productos', 'peso_gramos')
