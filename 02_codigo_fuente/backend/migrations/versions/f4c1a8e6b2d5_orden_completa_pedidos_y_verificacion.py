"""orden con datos completos, pedidos que agrupan órdenes y verificación del abono

Revision ID: f4c1a8e6b2d5
Revises: e2a7c4d9f1b3
Create Date: 2026-11-16 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f4c1a8e6b2d5'
down_revision: Union[str, Sequence[str], None] = 'e2a7c4d9f1b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('clientes', sa.Column('nombre_completo', sa.String(150), nullable=True))
    op.add_column('clientes', sa.Column('telefono', sa.String(30), nullable=True))
    op.create_table(
        'pedidos',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('cliente_id', sa.Integer(), sa.ForeignKey('clientes.id'), nullable=False),
        sa.Column('usuario_id', sa.Integer(), sa.ForeignKey('usuarios.id'), nullable=True),
        sa.Column(
            'creado_en', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index('ix_pedidos_cliente_id', 'pedidos', ['cliente_id'])
    op.add_column('ordenes', sa.Column('pedido_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_ordenes_pedido_id', 'ordenes', 'pedidos', ['pedido_id'], ['id'])
    op.create_index('ix_ordenes_pedido_id', 'ordenes', ['pedido_id'])
    op.add_column('ordenes', sa.Column('peso_gramos', sa.Numeric(8, 2), nullable=True))
    op.add_column('ordenes', sa.Column('fecha_entrega_taller', sa.Date(), nullable=True))
    op.add_column('ordenes', sa.Column('fecha_entrega_cliente', sa.Date(), nullable=True))
    op.add_column('ordenes', sa.Column('total', sa.Numeric(10, 2), nullable=True))
    op.add_column('ordenes', sa.Column('abono', sa.Numeric(10, 2), nullable=True))
    op.add_column('ordenes', sa.Column('foto_referencia_url', sa.String(500), nullable=True))
    op.add_column('ordenes', sa.Column('verificada_usuario_id', sa.Integer(), nullable=True))
    op.add_column(
        'ordenes', sa.Column('verificada_en', sa.DateTime(timezone=True), nullable=True)
    )
    op.create_foreign_key(
        'fk_ordenes_verificada_usuario_id', 'ordenes', 'usuarios', ['verificada_usuario_id'], ['id']
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('fk_ordenes_verificada_usuario_id', 'ordenes', type_='foreignkey')
    for columna in (
        'verificada_en', 'verificada_usuario_id', 'foto_referencia_url', 'abono', 'total',
        'fecha_entrega_cliente', 'fecha_entrega_taller', 'peso_gramos',
    ):
        op.drop_column('ordenes', columna)
    op.drop_index('ix_ordenes_pedido_id', table_name='ordenes')
    op.drop_constraint('fk_ordenes_pedido_id', 'ordenes', type_='foreignkey')
    op.drop_column('ordenes', 'pedido_id')
    op.drop_index('ix_pedidos_cliente_id', table_name='pedidos')
    op.drop_table('pedidos')
    op.drop_column('clientes', 'telefono')
    op.drop_column('clientes', 'nombre_completo')
