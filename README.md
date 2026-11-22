# sqlalchemy-materialize

A **SQLAlchemy dialect** for **Materialize**, using the psycopg2 driver.
Connect with a `materialize+psycopg2://` URL and inspect columns and indexes
through Materialize's system catalogs.

---

## Why this package exists

Materialize provides a PostgreSQL-compatible connection interface, but its system
catalogs differ from PostgreSQL's. This package extends SQLAlchemy's PostgreSQL
dialect with reflection methods that query Materialize's catalogs.

The connection and SQL compilation behavior come from SQLAlchemy's PostgreSQL
and psycopg2 dialects. Materialize-specific column and index reflection is
implemented in this package.

---

## Installation

```bash
pip install sqlalchemy-materialize
```

This also installs **SQLAlchemy 2.0** (`>=2.0,<2.1`) and **psycopg2** (`>=2.9`).
Installing psycopg2 from source may require PostgreSQL development libraries and
a C compiler.

---

## Usage

```python
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

url = URL.create(
    "materialize+psycopg2",
    username="YOUR_USER",
    password="YOUR_PASSWORD",
    host="YOUR_HOST",
    port=6875,
    database="materialize",
    query={"sslmode": "require"},
)

engine = create_engine(url)

with engine.connect() as connection:
    print(connection.execute(text("SELECT 1")).scalar_one())

engine.dispose()
```

Replace the placeholders with your connection details. Adjust the port, database,
and SSL settings for your deployment. `URL.create()` handles special characters
in passwords without manual URL encoding.

---

## What it adds

| Feature | Description |
| --- | --- |
| `materialize+psycopg2://` connection URL | Registers the Materialize dialect with SQLAlchemy using the psycopg2 driver. |
| Column reflection | Reads column names, types, nullability, and defaults from Materialize's catalogs. |
| Index reflection | Reflects column indexes and expression indexes, including the order of indexed columns. |
| Bulk reflection | Implements `get_multi_columns` and `get_multi_indexes` for inspecting multiple relations. |
| Relation filtering | Supports schema, relation-name, object-kind, and temporary-object scope filters for column and index reflection. |
| Tables and views | Reflection lookup supports tables, views, and materialized views. |
| Constraint reflection | Returns empty check-constraint and foreign-key lists for matching Materialize relations. |

For example, inspect an existing relation using a configured engine:

```python
from sqlalchemy import inspect

inspector = inspect(engine)
columns = inspector.get_columns("my_table", schema="public")
indexes = inspector.get_indexes("my_table", schema="public")
```

Replace `my_table` and `public` with your relation and schema. Run inspection
before disposing of the engine.

---

## Known limits

- Types not recognized by the inherited PostgreSQL type parser produce a warning
  and are reflected as SQLAlchemy `NullType`.
- Check-constraint and foreign-key reflection returns empty lists for matching
  relations. To inspect constraints in an upstream database, connect directly to
  it using its corresponding dialect.
- This dialect raises `NotImplementedError` for two-phase commit recovery.
- SQLAlchemy statement caching is disabled for this dialect.

---

## Development

From the repository root, install the package in editable mode:

```bash
python -m pip install -e .
python -m pip install pytest
```

Run the tests:

```bash
python -m pytest
```

---

## License

This project is licensed under the **Apache License 2.0**. See [LICENSE](LICENSE)
for the full license text.
