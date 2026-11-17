"""historial con tipo y nota: modificaciones, retrocesos y cancelaciones de órdenes (JOY-23)

Revision ID: a8d3f6c1e9b4
Revises: f4c1a8e6b2d5
Create Date: 2026-11-17 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a8d3f6c1e9b4'
down_revision: Union[str, Sequence[str], None] = 'f4c1a8e6b2d5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Lo registrado hasta hoy son avances de etapa: quedan con tipo "etapa".
    op.add_column(
        'historial_etapas',
        sa.Column('tipo', sa.String(20), nullable=False, server_default='etapa'),
    )
    op.add_column('historial_etapas', sa.Column('nota', sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('historial_etapas', 'nota')
    op.drop_column('historial_etapas', 'tipo')
