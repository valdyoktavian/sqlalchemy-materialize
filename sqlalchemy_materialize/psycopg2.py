from sqlalchemy import bindparam, text

# sqlalchemy_materialize/psycopg2.py
from sqlalchemy.dialects.postgresql.psycopg2 import PGDialect_psycopg2
from sqlalchemy.engine.reflection import ObjectKind, ObjectScope

from .base import MaterializeDialect


class MaterializeDialect_psycopg2(
    MaterializeDialect,
    PGDialect_psycopg2,
):
    driver = "psycopg2"
    supports_statement_cache = False

    # get_columns, get_indexes, get_foreign_keys are just wrapper that calls
    # the get_multi_xxx version of them    
  
    # Helper function. Needed for filtering relations for get_multi_columns and get_multi_indexes
    def _get_relation_ids(self, connection, schema, filter_names, scope, kind):
        """Return a name-to-ID mapping filtered by schema, names, scope, and kind.

        Prefer temporary relations when matching names overlap.
        """
        # Select catalogs for the requested relation kinds.
        catalogs = [
            catalog
            for object_kind, catalog in (
                (ObjectKind.TABLE, "mz_tables"),
                (ObjectKind.VIEW, "mz_views"),
                (ObjectKind.MATERIALIZED_VIEW, "mz_materialized_views"),
            )
            if object_kind in kind
        ]
        
        if not catalogs or not scope:
            return {}

        # Unqualified names follow search-path visibility, including session
        # temporary objects. Explicit schemas still exclude other sessions' temps.
        
        schema_filter = (
            "(r.schema_id = '0' OR pg_table_is_visible(r.oid))"
            if schema is None
            else "r.schema_id = '0'"
            if schema == "mz_temp"
            else "s.name = :schema"
        )
        
        # Add scope filter based on 'scope'
        # In Materialize, schema_id of temp table is '0'
        scope_filter = "TRUE"
        if scope == ObjectScope.DEFAULT:
            scope_filter = "r.schema_id <> '0'"
        elif scope == ObjectScope.TEMPORARY:
            scope_filter = "r.schema_id = '0'"

        
        # Catalog identifiers come only from the fixed mapping above.
        relations_sql = " UNION ALL ".join(
            f"SELECT id, oid, name, schema_id FROM mz_catalog.{catalog}"
            for catalog in catalogs
        )
        existing_relations = connection.execute(text(f"""
            SELECT r.id, r.name, r.schema_id = '0' AS is_temp
            FROM ({relations_sql}) AS r
            LEFT JOIN mz_catalog.mz_schemas AS s ON r.schema_id = s.id
            LEFT JOIN mz_catalog.mz_databases AS d ON s.database_id = d.id
            WHERE ({schema_filter}) AND ({scope_filter})
                AND (d.name = current_database() 
                    OR r.schema_id = '0')
        """), {"schema": schema}).mappings().all()
        
        
        # If there's two tables of the same name i.e. one is TEMP
        # pick the TEMP one.
    
        relation_id_by_name = {}
        for row in existing_relations:
            if row["name"] in relation_id_by_name:
                relation_id_by_name[row["name"]] = row["id"] if row["is_temp"] else relation_id_by_name[row["name"]]
            else:
                relation_id_by_name[row["name"]] = row["id"]
        
        if filter_names is None:
            filter_names = sorted(relation_id_by_name)
        else:
            filter_names = sorted(set(relation_id_by_name).intersection(filter_names))
        
        return {name: relation_id_by_name[name] for name in filter_names}


    
    def get_multi_columns(self, connection, schema, filter_names, scope, kind, **kw):
        """Return ((schema, relation_name), columns) pairs for matching relations."""
        relation_id_by_name = self._get_relation_ids(
            connection, schema, filter_names, scope, kind
        )
        if not relation_id_by_name:
            return {}.items()
        relation_ids = list(relation_id_by_name.values())
        name_by_id = {rel_id: name for name, rel_id in relation_id_by_name.items()}
        columns = {(schema, name): [] for name in relation_id_by_name}
        
        query = text("""
            SELECT
                id, name, format_type(type_oid, type_mod) AS type, nullable, "default"
            FROM mz_catalog.mz_columns
            WHERE id IN :relation_ids
            ORDER BY id, position
        """).bindparams(bindparam("relation_ids", expanding=True))
        
        result = connection.execute(query, {
            "relation_ids": relation_ids,
        }).mappings().all()

        for row in result:
            relation_name = name_by_id[row["id"]]
            columns[(schema, relation_name)].append({
                "name": row["name"],
                # This parser converts type strings without querying PG catalogs.
                # Unknown Materialize-specific types warn and become NullType.
                "type": self._reflect_type(
                    row["type"], {}, {},
                    type_description=f"column '{relation_name}.{row['name']}'",
                    collation=None,
                ),
                "nullable": bool(row["nullable"]),
                "default": row["default"],
            })
        return columns.items()

    def get_multi_indexes(
        self, connection, schema, filter_names, scope, kind, **kw
    ):
        """Reflect indexes for relations matching the requested filters.

        @param connection: SQLAlchemy connection used to query the catalogs.
        @param schema: Schema to inspect, or None for unqualified-name lookup.
        @param filter_names: Relation names to include, or None for all relations
            matching the schema, scope, and kind filters.
        @param scope: ObjectScope flag selecting non-temporary objects,
            temporary objects, or both.
        @param kind: ObjectKind flag selecting tables, views, materialized views,
            or a combination of these kinds.
        @param kw: Additional keyword arguments supplied by SQLAlchemy.
        @return: An iterable of ((schema, table_name), indexes) pairs, where
            indexes is a list of reflected index dictionaries. Relations without
            indexes are included with an empty list.
        """

        relation_id_by_name = self._get_relation_ids(
            connection, schema, filter_names, scope, kind
        )
        if not relation_id_by_name:
            return {}.items()
        filter_names = list(relation_id_by_name)
        relation_ids = list(relation_id_by_name.values())

        # Query
        # TODO: Refactor by moving query to psycopg2.py, make _xxxx_query
        query = text("""
            SELECT
                r.name AS table_name,
                i.id AS index_id,
                i.name AS index_name,
                ic.index_position,
                col.name AS column_name,
                ic.on_expression
            FROM mz_catalog.mz_indexes AS i
            JOIN mz_catalog.mz_relations AS r
                ON i.on_id = r.id
            JOIN mz_catalog.mz_index_columns AS ic
                ON ic.index_id = i.id
            LEFT JOIN mz_catalog.mz_columns AS col
                ON col.id = r.id
                AND col.position = ic.on_position
            WHERE r.id IN :relation_ids
            ORDER BY r.name, i.id, ic.index_position
        """).bindparams(bindparam("relation_ids", expanding=True))
        
        result = connection.execute(query, {
            "relation_ids": relation_ids,
        }).mappings().all()
        
        
        parsed = {}
        prev_id = None
        prev_table_name = None
        
        for row in result:
            table_name = row["table_name"]
            index_id = row["index_id"]
            name = row["index_name"]
            col_name = row["column_name"]
            on_exp = row["on_expression"]
            
            # "Expressions" can't be None, instead change it to its column name
            on_exp = on_exp if on_exp is not None else col_name
            
            
            if prev_table_name != table_name:
                parsed[(schema, table_name)] = [] 
                
            # Check if the column belongs to the previous index (multi-column index)
            if prev_id != index_id:
                # Base format to be filled after
                parsed[(schema, table_name)].append(
                    {
                        "name": name,       
                        "column_names": [], 
                        "expressions": [],
                        "unique": False, 
                    }
                )
                
                
            # Works for both multi-col-index and single-col-index
            parsed[(schema, table_name)][-1]["column_names"].append(col_name)
            parsed[(schema, table_name)][-1]["expressions"].append(on_exp)
                
            prev_id = index_id
            prev_table_name = table_name
        
        # Remove expressions if there's None
        for indexes in parsed.values():
            for index in indexes:
                if None not in index["column_names"]:
                    del index["expressions"]
    
        # TODO: Could be refactored, maybe put it at top
        # Add the key, value pair for table with no index
        for table_name in filter_names:
            if (schema, table_name) not in parsed:
                parsed[(schema, table_name)] = []
            
        return parsed.items()
            
        

    # get_pk_constraint still uses supported pg_catalog's table, so we can omit this
    # def get_pk_constraint(self, connection, table_name, schema=None, **kw):
    #     '''
    #     Materialize doesn't support primary key for tables built in Materialize.
    #     For other database like PostgreSQL, MySQL that is upstreamed to Materialize,
    #     you should connect directly to it with its corresponding SQLALchemy dialect
    #     '''
    #     return []   
    

    def get_multi_check_constraints(self, connection, schema, filter_names, scope, kind, **kw):
        '''
        Materialize doesn't support constraint for tables built in Materialize.
        For other database like PostgreSQL, MySQL that is upstreamed to Materialize,
        you should connect directly to it with its corresponding SQLALchemy dialect
        '''
        relation_id_by_name = self._get_relation_ids(
            connection, schema, filter_names, scope, kind
        )
        return {(schema, name): [] for name in relation_id_by_name}.items()


    def get_multi_foreign_keys(
        self, connection, schema, filter_names, scope, kind, 
        postgresql_ignore_search_path=False, **kw
    ):
        '''
        Materialize doesn't support foreign key for tables built in Materialize.
        For other database like PostgreSQL, MySQL that is upstreamed to Materialize,
        you should connect directly to it with its corresponding SQLALchemy dialect
        '''
        relation_id_by_name = self._get_relation_ids(
            connection, schema, filter_names, scope, kind
        )
        return {(schema, name): [] for name in relation_id_by_name}.items()
