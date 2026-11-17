"""autor del mensaje (para distinguir las respuestas del asesor)

Revision ID: c9e4a7b1d3f2
Revises: b7d2e5f4a1c8
Create Date: 2026-11-10 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c9e4a7b1d3f2'
down_revision: Union[str, Sequence[str], None] = 'b7d2e5f4a1c8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('mensajes', sa.Column('autor', sa.String(20), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('mensajes', 'autor')
