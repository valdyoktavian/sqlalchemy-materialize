from sqlalchemy import create_engine
from sqlalchemy_materialize.psycopg2 import MaterializeDialect_psycopg2


def test_dialect_registration():
    engine = create_engine(
        "materialize+psycopg2://user:password@localhost:6875/materialize"
    )
    try:
        assert isinstance(engine.dialect, MaterializeDialect_psycopg2)
        assert engine.dialect.name == "materialize"
        assert engine.dialect.driver == "psycopg2"
    finally:
        engine.dispose()