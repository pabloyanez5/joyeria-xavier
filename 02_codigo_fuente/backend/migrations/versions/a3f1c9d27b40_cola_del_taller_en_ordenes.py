"""cola del taller en ordenes

Revision ID: a3f1c9d27b40
Revises: 54c6aae80b13
Create Date: 2026-11-05 19:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3f1c9d27b40'
down_revision: Union[str, Sequence[str], None] = '54c6aae80b13'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'ordenes',
        sa.Column('acuse_pendiente', sa.Boolean(), server_default=sa.true(), nullable=False),
    )
    op.add_column(
        'ordenes', sa.Column('publicada_en', sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('ordenes', 'publicada_en')
    op.drop_column('ordenes', 'acuse_pendiente')
