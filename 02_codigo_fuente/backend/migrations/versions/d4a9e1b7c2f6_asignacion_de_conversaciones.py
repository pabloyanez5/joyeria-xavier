"""asignación de conversaciones escaladas a un asesor (JOY-84)

Revision ID: d4a9e1b7c2f6
Revises: c3f8a2d6e4b1
Create Date: 2026-11-25 18:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4a9e1b7c2f6'
down_revision: Union[str, Sequence[str], None] = 'c3f8a2d6e4b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'conversaciones',
        sa.Column('asesor_id', sa.Integer(), sa.ForeignKey('usuarios.id'), nullable=True),
    )
    op.add_column('conversaciones', sa.Column('asignada_en', sa.DateTime(timezone=True), nullable=True))
    op.create_index('ix_conversaciones_asesor_id', 'conversaciones', ['asesor_id'])
    op.create_table(
        'asignaciones_conversacion',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('conversacion_id', sa.Integer(), sa.ForeignKey('conversaciones.id'), nullable=False),
        sa.Column('asesor_id', sa.Integer(), sa.ForeignKey('usuarios.id'), nullable=True),
        sa.Column('usuario_id', sa.Integer(), sa.ForeignKey('usuarios.id'), nullable=True),
        sa.Column('tipo', sa.String(20), nullable=False),
        sa.Column(
            'creado_en', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        'ix_asignaciones_conversacion_conversacion_id',
        'asignaciones_conversacion',
        ['conversacion_id'],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_asignaciones_conversacion_conversacion_id', table_name='asignaciones_conversacion')
    op.drop_table('asignaciones_conversacion')
    op.drop_index('ix_conversaciones_asesor_id', table_name='conversaciones')
    op.drop_column('conversaciones', 'asignada_en')
    op.drop_column('conversaciones', 'asesor_id')
