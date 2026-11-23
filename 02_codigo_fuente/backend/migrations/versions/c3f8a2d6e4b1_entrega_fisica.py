"""entrega física de la orden: quién la registró y cuándo (JOY-19)

Revision ID: c3f8a2d6e4b1
Revises: b7e2d4f9a1c3
Create Date: 2026-11-23 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3f8a2d6e4b1'
down_revision: Union[str, Sequence[str], None] = 'b7e2d4f9a1c3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'ordenes',
        sa.Column('entrega_usuario_id', sa.Integer(), sa.ForeignKey('usuarios.id'), nullable=True),
    )
    op.add_column('ordenes', sa.Column('entregada_en', sa.DateTime(timezone=True), nullable=True))
    # Las órdenes ya entregadas toman el dato de su paso «entregada» en el historial.
    op.execute(
        """
        UPDATE ordenes SET
            entregada_en = h.creado_en,
            entrega_usuario_id = h.usuario_id
        FROM historial_etapas h
        WHERE h.orden_id = ordenes.id
          AND h.etapa = 'entregada'
          AND h.tipo = 'etapa'
          AND ordenes.etapa_actual = 'entregada'
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('ordenes', 'entregada_en')
    op.drop_column('ordenes', 'entrega_usuario_id')
