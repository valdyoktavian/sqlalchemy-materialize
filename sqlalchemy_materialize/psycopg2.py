# sqlalchemy_materialize/psycopg2.py
from sqlalchemy.dialects.postgresql.psycopg2 import PGDialect_psycopg2

from .base import MaterializeDialect


class MaterializeDialect_psycopg2(
    MaterializeDialect,
    PGDialect_psycopg2,
):
    driver = "psycopg2"
    supports_statement_cache = False
    
    # TODO: Override functions that are not supported
    # - pg_opclass from get_indexes() or get_multi_indexes()
    # - more like get_foreign_keys...
    
    def get_indexes(self, connection, table_name, schema= None, **kw):
        return []
    
    def get_multi_indexes(self, connection, schema, filter_names, **kw):
        return []
    