from sqlalchemy import func, select

from app.models import Producto
from app.seed import CATALOGO, cargar


def test_seed_crea_el_catalogo_y_no_duplica(session):
    assert cargar(session) == len(CATALOGO)
    assert cargar(session) == 0
    total = session.scalar(select(func.count()).select_from(Producto))
    assert total == len(CATALOGO)