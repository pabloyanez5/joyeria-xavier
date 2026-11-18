"""registro de intentos bloqueados por la seguridad del agente (JOY-74)

Revision ID: b7e2d4f9a1c3
Revises: a8d3f6c1e9b4
Create Date: 2026-11-18 19:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7e2d4f9a1c3'
down_revision: Union[str, Sequence[str], None] = 'a8d3f6c1e9b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'intentos_bloqueados',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column(
            'creado_en', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column('cliente_id', sa.Integer(), sa.ForeignKey('clientes.id'), nullable=True),
        sa.Column('mensaje_id', sa.Integer(), sa.ForeignKey('mensajes.id'), nullable=True),
        sa.Column('canal', sa.String(20), nullable=False),
        sa.Column('motivo', sa.String(30), nullable=False),
        sa.Column('regla', sa.String(40), nullable=True),
    )
    op.create_index('ix_intentos_bloqueados_creado_en', 'intentos_bloqueados', ['creado_en'])
    op.create_index('ix_intentos_bloqueados_cliente_id', 'intentos_bloqueados', ['cliente_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_intentos_bloqueados_cliente_id', table_name='intentos_bloqueados')
    op.drop_index('ix_intentos_bloqueados_creado_en', table_name='intentos_bloqueados')
    op.drop_table('intentos_bloqueados')
