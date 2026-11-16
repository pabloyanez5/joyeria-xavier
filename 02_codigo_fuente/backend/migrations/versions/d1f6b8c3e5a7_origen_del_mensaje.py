"""origen del mensaje (qué redactó la respuesta: modelo, respaldo, reglas, menu o guardrail)

Revision ID: d1f6b8c3e5a7
Revises: c9e4a7b1d3f2
Create Date: 2026-11-16 19:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd1f6b8c3e5a7'
down_revision: Union[str, Sequence[str], None] = 'c9e4a7b1d3f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('mensajes', sa.Column('origen', sa.String(20), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('mensajes', 'origen')
