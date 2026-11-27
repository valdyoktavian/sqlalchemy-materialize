"""Index reflection scope tests against a fake mz_catalog.

The fixture mirrors catalog behavior observed on Materialize v26.51.1:

* Temporary objects have ``schema_id = '0'``. There is no ``mz_temp`` row in
  ``mz_schemas``, so joins to mz_schemas / mz_databases yield NULL for them.
* ``pg_table_is_visible(oid)`` is NULL for temporary objects, and TRUE for a
  search-path object even when a temporary object with the same name shadows it.
* Temporary objects of *every* session appear in the catalog and cannot be
  told apart, so "other session" temp objects are not modelled here.
* Indexes cannot be created on temporary objects ("non-temporary items cannot
  depend on temporary item"), so temporary relations never have indexes.
* In ``mz_index_columns`` exactly one of ``on_position`` / ``on_expression`` is
  non-NULL; positions are 1-based.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine.reflection import ObjectKind, ObjectScope

from sqlalchemy_materialize.psycopg2 import MaterializeDialect_psycopg2

TEMP = "0"

DATABASES = [("u1", "materialize"), ("u2", "other_db")]

SCHEMAS = [
    # id, database_id, name
    ("u3", "u1", "public"),
    ("u4", "u1", "analytics"),  # not on the search path
    ("u5", "u2", "public"),     # public schema of a different database
]

RELATIONS = [
    # id, oid, name, schema_id, catalog, type, visible
    ("u1", 20201, "shared", "u3", "mz_tables", "table", True),
    ("u3", 20203, "regular", "u3", "mz_tables", "table", True),
    ("u5", 20205, "v", "u3", "mz_views", "view", True),
    ("u7", 20207, "mv", "u3", "mz_materialized_views", "materialized-view", True),
    ("u8", 20208, "report", "u4", "mz_tables", "table", False),
    ("u10", 20210, "elsewhere", "u5", "mz_tables", "table", False),
    ("u11", 20211, "a_only", TEMP, "mz_tables", "table", None),
    ("u12", 20212, "shared", TEMP, "mz_tables", "table", None),  # shadows public.shared
    ("u14", 20214, "temp_view", TEMP, "mz_views", "view", None),
]

COLUMNS = [
    # relation id, position, name
    ("u1", 1, "value"),
    ("u3", 1, "a"),
    ("u3", 2, "b"),
    ("u5", 1, "x"),
    ("u7", 1, "x"),
    ("u8", 1, "value"),
    ("u10", 1, "value"),
    ("u11", 1, "value"),
    ("u12", 1, "value"),
    ("u14", 1, "x"),
]

INDEXES = [
    # id, name, on_id, [(index_position, on_position, on_expression)]
    ("u2", "idx_shared", "u1", [(1, 1, None)]),
    ("u4", "idx_multi", "u3", [(1, 1, None), (2, None, "b + 1")]),
    ("u6", "idx_v", "u5", [(1, 1, None)]),
    ("u9", "idx_report", "u8", [(1, 1, None)]),
    ("u13", "idx_elsewhere", "u10", [(1, 1, None)]),
]

# Expected reflected indexes per relation name.
IDX_SHARED = {"name": "idx_shared", "column_names": ["value"], "unique": False}
IDX_MULTI = {
    "name": "idx_multi",
    "column_names": ["a", None],
    "expressions": ["a", "b + 1"],
    "unique": False,
}
IDX_V = {"name": "idx_v", "column_names": ["x"], "unique": False}
IDX_REPORT = {"name": "idx_report", "column_names": ["value"], "unique": False}


@pytest.fixture
def catalog_connection():
    engine = create_engine("sqlite://")
    visibility = {oid: visible for _, oid, *_, visible in RELATIONS}
    with engine.connect() as connection:
        dbapi = connection.connection.driver_connection
        dbapi.create_function("current_database", 0, lambda: "materialize")
        dbapi.create_function("pg_table_is_visible", 1, visibility.get)
        connection.exec_driver_sql("ATTACH DATABASE ':memory:' AS mz_catalog")
        relation_cols = "id TEXT, oid INTEGER, schema_id TEXT, name TEXT"
        definitions = {
            "mz_databases": "id TEXT, oid INTEGER, name TEXT",
            "mz_schemas": "id TEXT, oid INTEGER, database_id TEXT, name TEXT",
            "mz_tables": relation_cols,
            "mz_sources": relation_cols,
            "mz_views": relation_cols,
            "mz_materialized_views": relation_cols,
            "mz_relations": relation_cols + ", type TEXT",
            "mz_columns": "id TEXT, name TEXT, position INTEGER",
            "mz_indexes": "id TEXT, oid INTEGER, name TEXT, on_id TEXT",
            "mz_index_columns": (
                "index_id TEXT, index_position INTEGER, "
                "on_position INTEGER, on_expression TEXT"
            ),
        }
        for table, columns in definitions.items():
            connection.exec_driver_sql(f"CREATE TABLE mz_catalog.{table} ({columns})")

        def insert(table, *values):
            marks = ", ".join("?" * len(values))
            connection.exec_driver_sql(
                f"INSERT INTO mz_catalog.{table} VALUES ({marks})", values
            )

        for n, (db_id, name) in enumerate(DATABASES):
            insert("mz_databases", db_id, 20000 + n, name)
        for n, (schema_id, db_id, name) in enumerate(SCHEMAS):
            insert("mz_schemas", schema_id, 20100 + n, db_id, name)
        for rel_id, oid, name, schema_id, catalog, rel_type, _ in RELATIONS:
            insert(catalog, rel_id, oid, schema_id, name)
            insert("mz_relations", rel_id, oid, schema_id, name, rel_type)
        for rel_id, position, name in COLUMNS:
            insert("mz_columns", rel_id, name, position)
        for n, (index_id, name, on_id, columns) in enumerate(INDEXES):
            insert("mz_indexes", index_id, 20300 + n, name, on_id)
            for column in columns:
                insert("mz_index_columns", index_id, *column)
        yield connection
    engine.dispose()


@pytest.mark.parametrize("schema,scope,kind,filters,expected", [
    # Search path (schema=None), regular objects only.
    (None, ObjectScope.DEFAULT, ObjectKind.ANY, None,
     {"shared": [IDX_SHARED], "regular": [IDX_MULTI], "v": [IDX_V], "mv": []}),
    (None, ObjectScope.DEFAULT, ObjectKind.TABLE, None,
     {"shared": [IDX_SHARED], "regular": [IDX_MULTI]}),
    (None, ObjectScope.DEFAULT, ObjectKind.VIEW, None, {"v": [IDX_V]}),
    (None, ObjectScope.DEFAULT, ObjectKind.MATERIALIZED_VIEW, None, {"mv": []}),
    (None, ObjectScope.DEFAULT, ObjectKind.TABLE, ["shared", "missing"],
     {"shared": [IDX_SHARED]}),
    # Temporary objects: always present, never indexed.
    (None, ObjectScope.TEMPORARY, ObjectKind.ANY, None,
     {"a_only": [], "shared": [], "temp_view": []}),
    (None, ObjectScope.TEMPORARY, ObjectKind.TABLE, None,
     {"a_only": [], "shared": []}),
    (None, ObjectScope.TEMPORARY, ObjectKind.MATERIALIZED_VIEW, None, {}),
    # Both scopes: the temporary "shared" shadows public.shared, so the
    # unqualified name resolves to the (unindexed) temporary table.
    (None, ObjectScope.ANY, ObjectKind.ANY, None,
     {"shared": [], "regular": [IDX_MULTI], "v": [IDX_V], "mv": [],
      "a_only": [], "temp_view": []}),
    # Explicit schemas.
    ("public", ObjectScope.DEFAULT, ObjectKind.ANY, None,
     {"shared": [IDX_SHARED], "regular": [IDX_MULTI], "v": [IDX_V], "mv": []}),
    ("public", ObjectScope.TEMPORARY, ObjectKind.ANY, None, {}),
    ("analytics", ObjectScope.DEFAULT, ObjectKind.TABLE, None,
     {"report": [IDX_REPORT]}),
    ("mz_temp", ObjectScope.ANY, ObjectKind.TABLE, ["shared", "a_only", "missing"],
     {"shared": [], "a_only": []}),
    ("mz_temp", ObjectScope.DEFAULT, ObjectKind.ANY, None, {}),
    # Empty filter list.
    (None, ObjectScope.ANY, ObjectKind.ANY, [], {}),
])
def test_index_scope(catalog_connection, schema, scope, kind, filters, expected):
    dialect = MaterializeDialect_psycopg2()
    result = dict(dialect.get_multi_indexes(catalog_connection, schema, filters, scope, kind))
    assert result == {(schema, name): indexes for name, indexes in expected.items()}
