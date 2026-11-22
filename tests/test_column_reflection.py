from unittest.mock import Mock

import pytest
from sqlalchemy import Integer, Numeric, String, create_engine
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.engine.reflection import ObjectKind, ObjectScope
from sqlalchemy.exc import SAWarning
from sqlalchemy.sql.sqltypes import NullType

from sqlalchemy_materialize.psycopg2 import MaterializeDialect_psycopg2


def test_columns_by_relation_id():
    engine = create_engine("sqlite://")
    dialect = MaterializeDialect_psycopg2()
    dialect._get_relation_ids = Mock(return_value={"users": "u1", "view": "u2", "empty": "u3"})
    with engine.connect() as connection:
        # Stand in for the server formatter; verify both OID and modifier are
        # supplied and that the formatted result reaches SQLAlchemy's parser.
        formatted_types = {
            (1700, 655366): "numeric(10,2)",
            (23, -1): "integer",
            (1015, 24): "character varying(20)[]",
            (99999, -1): "custom_type",
        }
        connection.connection.driver_connection.create_function(
            "format_type", 2, lambda oid, modifier: formatted_types[(oid, modifier)]
        )
        connection.exec_driver_sql("ATTACH DATABASE ':memory:' AS mz_catalog")
        connection.exec_driver_sql('CREATE TABLE mz_catalog.mz_columns (id TEXT, name TEXT, position INTEGER, type_oid INTEGER, type_mod INTEGER, nullable BOOLEAN, "default" TEXT)')
        connection.exec_driver_sql('INSERT INTO mz_catalog.mz_columns VALUES (?, ?, ?, ?, ?, ?, ?)', [
            ("u1", "amount", 2, 1700, 655366, True, "0"),
            ("u1", "id", 1, 23, -1, False, None),
            ("u2", "names", 1, 1015, 24, True, None),
            ("unselected", "ignored", 1, 23, -1, False, None),
        ])
        result = dict(dialect.get_multi_columns(connection, None, None, ObjectScope.ANY, ObjectKind.ANY))
        assert set(result) == {(None, "users"), (None, "view"), (None, "empty")}
        assert result[(None, "empty")] == []
        columns = result[(None, "users")]
        assert [col["name"] for col in columns] == ["id", "amount"]
        assert isinstance(columns[0]["type"], Integer)
        assert columns[0]["nullable"] is False
        assert columns[0]["default"] is None
        assert isinstance(columns[1]["type"], Numeric)
        assert (columns[1]["type"].precision, columns[1]["type"].scale) == (10, 2)
        assert columns[1]["nullable"] is True
        assert columns[1]["default"] == "0"
        array = result[(None, "view")][0]["type"]
        assert isinstance(array, ARRAY)
        assert isinstance(array.item_type, String)
        assert array.item_type.length == 20
        # The inherited single-relation wrapper also uses this implementation.
        assert dialect.get_columns(connection, "users")[0]["name"] == "id"
        connection.exec_driver_sql("UPDATE mz_catalog.mz_columns SET type_oid = 99999, type_mod = -1 WHERE id = 'u2'")
        with pytest.warns(SAWarning, match="Did not recognize type"):
            result = dict(dialect.get_multi_columns(connection, None, None, ObjectScope.ANY, ObjectKind.ANY))
        assert isinstance(result[(None, "view")][0]["type"], NullType)
    engine.dispose()


def test_no_matching_relations_skips_column_query():
    dialect = MaterializeDialect_psycopg2()
    dialect._get_relation_ids = Mock(return_value={})
    connection = Mock()
    assert dict(dialect.get_multi_columns(connection, "public", [], ObjectScope.DEFAULT, ObjectKind.TABLE)) == {}
    connection.execute.assert_not_called()
