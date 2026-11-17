"""usuarios con clave y rol dirección; quién confirmó el acuse y quién respondió al cliente

Revision ID: e2a7c4d9f1b3
Revises: d1f6b8c3e5a7
Create Date: 2026-11-16 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e2a7c4d9f1b3'
down_revision: Union[str, Sequence[str], None] = 'd1f6b8c3e5a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('usuarios', sa.Column('clave_hash', sa.String(255), nullable=True))
    op.drop_constraint('ck_usuarios_rol', 'usuarios', type_='check')
    op.create_check_constraint(
        'ck_usuarios_rol', 'usuarios', "rol IN ('asesor', 'taller', 'direccion', 'admin')"
    )
    op.add_column('mensajes', sa.Column('usuario_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_mensajes_usuario_id', 'mensajes', 'usuarios', ['usuario_id'], ['id']
    )
    op.add_column('ordenes', sa.Column('acuse_usuario_id', sa.Integer(), nullable=True))
    op.add_column('ordenes', sa.Column('acuse_en', sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(
        'fk_ordenes_acuse_usuario_id', 'ordenes', 'usuarios', ['acuse_usuario_id'], ['id']
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('fk_ordenes_acuse_usuario_id', 'ordenes', type_='foreignkey')
    op.drop_column('ordenes', 'acuse_en')
    op.drop_column('ordenes', 'acuse_usuario_id')
    op.drop_constraint('fk_mensajes_usuario_id', 'mensajes', type_='foreignkey')
    op.drop_column('mensajes', 'usuario_id')
    op.drop_constraint('ck_usuarios_rol', 'usuarios', type_='check')
    op.create_check_constraint(
        'ck_usuarios_rol', 'usuarios', "rol IN ('asesor', 'taller', 'admin')"
    )
    op.drop_column('usuarios', 'clave_hash')
