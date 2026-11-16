# sqlalchemy_materialize/base.py
from sqlalchemy.dialects.postgresql.base import PGDialect


class MaterializeDialect(PGDialect):
    name = "materialize"
    supports_statement_cache = False