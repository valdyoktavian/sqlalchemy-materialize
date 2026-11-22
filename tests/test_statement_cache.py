"""Compilation regressions and optional read-only Materialize cache tests."""
import os

import pytest
from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, Date, Integer, Numeric, String, bindparam, cast, column, create_engine, event, literal, select, table, union_all
from sqlalchemy.engine.reflection import ObjectKind, ObjectScope
from sqlalchemy_materialize.base import MaterializeDialect
from sqlalchemy.dialects import registry
from sqlalchemy.engine.interfaces import CacheStats

from sqlalchemy_materialize.psycopg2 import MaterializeDialect_psycopg2


def test_both_dialects_enable_caching():
    assert MaterializeDialect.__dict__["supports_statement_cache"] is True
    assert MaterializeDialect_psycopg2.__dict__["supports_statement_cache"] is True


@pytest.mark.parametrize("values", [([1], [2, 3]), ([1, 2], []), ([], [4])])
def test_cached_expanding_parameters(values):
    dialect = MaterializeDialect_psycopg2()
    cache = {}
    relation = table("example", column("id", Integer))
    compiled_statements = []
    for ids in values:
        statement = select(relation.c.id).where(relation.c.id.in_(ids))
        compiled, extracted, status = statement._compile_w_cache(
            dialect, compiled_cache=cache, column_keys=[]
        )
        params = compiled.construct_params(extracted_parameters=extracted)
        expanded = compiled.construct_expanded_state(params)
        fresh = statement.compile(dialect=dialect, compile_kwargs={"render_postcompile": True})
        assert expanded.statement == str(fresh)
        assert expanded.parameters == fresh.params
        compiled_statements.append((compiled, status))
    assert compiled_statements[0][0] is compiled_statements[1][0]
    assert [item[1] for item in compiled_statements] == [CacheStats.CACHE_MISS, CacheStats.CACHE_HIT]


def test_cached_limit_offset_uses_current_values():
    dialect = MaterializeDialect_psycopg2()
    cache = {}
    relation = table("example", column("id", Integer))
    for limit, offset in [(2, 0), (5, 3), (1, 9)]:
        statement = select(relation.c.id).order_by(relation.c.id).limit(limit).offset(offset)
        compiled, extracted, status = statement._compile_w_cache(
            dialect, compiled_cache=cache, column_keys=[]
        )
        fresh = statement.compile(dialect=dialect)
        assert str(compiled) == str(fresh)
        assert compiled.construct_params(extracted_parameters=extracted) == fresh.params
        assert status is (CacheStats.CACHE_MISS if offset == 0 else CacheStats.CACHE_HIT)
    assert len(cache) == 1


@pytest.fixture
def live_engine():
    """Read-only smoke test; no tables are created or modified."""
    url = os.environ.get("MATERIALIZE_TEST_URL")
    if not url:
        pytest.skip("Set MATERIALIZE_TEST_URL to run against Materialize")
    registry.register("materialize.psycopg2", "sqlalchemy_materialize.psycopg2", "MaterializeDialect_psycopg2")
    engine = create_engine(url)
    assert isinstance(engine.dialect, MaterializeDialect_psycopg2)
    try:
        yield engine
    finally:
        engine.dispose()


def check_cached_and_uncached(engine, cases):
    hits = []

    def record(conn, cursor, statement, parameters, context, executemany):
        hits.append(context.cache_hit)

    event.listen(engine, "after_cursor_execute", record)
    try:
        with engine.connect() as connection:
            for cache in [{}, None]:
                connection = connection.execution_options(compiled_cache=cache)
                hits.clear()
                for statement, parameters, expected in cases:
                    assert connection.execute(statement, parameters).all() == expected
                if cache is not None:
                    assert hits == [CacheStats.CACHE_MISS] + [CacheStats.CACHE_HIT] * (len(cases) - 1)
                else:
                    assert all(hit is CacheStats.CACHING_DISABLED for hit in hits)
    finally:
        event.remove(engine, "after_cursor_execute", record)


def test_live_materialize_cache(live_engine):
    cases = [(select(bindparam("value", type_=Integer)), {"value": value}, [(value,)])
             for value in [10, 20, -3]]
    check_cached_and_uncached(live_engine, cases)


def numbers():
    return union_all(*(select(literal(value).label("n")) for value in range(1, 6))).subquery()


def test_live_pagination(live_engine):
    relation = numbers()
    cases = [(select(relation.c.n).order_by(relation.c.n).limit(limit).offset(offset), {},
              [(n,) for n in list(range(1, 6))[offset:offset + limit]])
             for limit, offset in [(2, 0), (3, 1), (0, 0), (1, 8)]]
    check_cached_and_uncached(live_engine, cases)


def test_live_expanding_in(live_engine):
    relation = numbers()
    cases = [(select(relation.c.n).where(relation.c.n.in_(ids)).order_by(relation.c.n), {},
              [(n,) for n in sorted(ids)])
             for ids in [[1], [2, 3], [], [4, 5]]]
    check_cached_and_uncached(live_engine, cases)


@pytest.mark.parametrize("type_,values", [
    (Integer(), [10, -3]),
    (String(), ["first", "second"]),
    (Boolean(), [True, False]),
    (Numeric(10, 2), [Decimal("12.34"), Decimal("56.78")]),
    (Date(), [date(2026, 1, 1), date(2026, 2, 2)]),
])
def test_live_types(live_engine, type_, values):
    cases = [(select(cast(bindparam("value", type_=type_), type_)), {"value": value}, [(value,)])
             for value in values]
    check_cached_and_uncached(live_engine, cases)


def test_live_reflection(live_engine):
    # Inspect existing visible relations only; create/drop no objects.
    def reflect(connection, names):
        args = dict(schema=None, filter_names=names,
                    scope=ObjectScope.DEFAULT, kind=ObjectKind.ANY)
        columns = dict(live_engine.dialect.get_multi_columns(connection, **args))
        indexes = dict(live_engine.dialect.get_multi_indexes(connection, **args))
        assert set(columns) == {(None, name) for name in names}
        assert all(columns.values())
        for relation_columns in columns.values():
            for col in relation_columns:
                col["type"] = str(col["type"])
        return columns, indexes

    hits = []
    def record(conn, cursor, statement, parameters, context, executemany):
        hits.append(context.cache_hit)

    with live_engine.connect() as connection:
        available = live_engine.dialect._get_relation_ids(
            connection, None, None, ObjectScope.DEFAULT, ObjectKind.ANY
        )
        if not available:
            pytest.skip("Reflection test needs an existing visible table or view")
        names = sorted(available)[:2]
        filters = [names[:1], names, []]
        event.listen(live_engine, "after_cursor_execute", record)
        try:
            connection = connection.execution_options(compiled_cache={})
            cached = [reflect(connection, names) for names in filters]
            assert CacheStats.CACHE_HIT in hits
            connection = connection.execution_options(compiled_cache=None)
            uncached = [reflect(connection, names) for names in filters]
            assert cached == uncached
        finally:
            event.remove(live_engine, "after_cursor_execute", record)
