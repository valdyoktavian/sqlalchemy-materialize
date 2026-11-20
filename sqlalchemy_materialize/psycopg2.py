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

    def get_multi_columns(self, connection, schema, filter_names, scope, kind, **kw):
        pass
    
  
    def get_multi_indexes(
        self, connection, schema, filter_names, scope, kind, **kw
    ):
        '''
        Returns: An iterable of ((schema, table_name), list of reflected index dictionaries) pairs.

        Replace the pg_opclass dependency in index reflection.

        PostgreSQL reference:
        https://github.com/sqlalchemy/sqlalchemy/blob/main/lib/sqlalchemy/dialects/postgresql/base.py
        '''
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
            return {}.items()

        # Unqualified names follow search-path visibility, including session
        # temporary objects. Explicit schemas still exclude other sessions' temps.
        
        # TODO: Nested ternary. May need to refactor, but should be good for now
        schema_filter = (
            "(r.schema_id = '0' OR pg_table_is_visible(r.oid))"
            if schema is None
            else "r.schema_id = '0'"
            if schema == "mz_temp"
            else "s.name = :schema"
        )
        scope_filter = "TRUE"
        if scope == ObjectScope.DEFAULT:
            scope_filter = "r.schema_id <> '0'"
        elif scope == ObjectScope.TEMPORARY:
            scope_filter = "r.schema_id = '0'"

        # TODO: Problem when tmp has the same name as non tmp table
        # Suggested solution: Take one :D but not both
        
        # Catalog identifiers come only from the fixed mapping above.
        relations_sql = " UNION ALL ".join(
            f"SELECT id, oid, name, schema_id FROM mz_catalog.{catalog}"
            for catalog in catalogs
        )
        existing_relations = connection.execute(text(f"""
            SELECT r.id, r.name
            FROM ({relations_sql}) AS r
            LEFT JOIN mz_catalog.mz_schemas AS s ON r.schema_id = s.id
            LEFT JOIN mz_catalog.mz_databases AS d ON s.database_id = d.id
            WHERE ({schema_filter}) AND ({scope_filter})
                AND (d.name = current_database() 
                    OR r.schema_id = '0')
        """), {"schema": schema}).mappings().all()
        existing_tables = {row["name"] for row in existing_relations}
        
        if filter_names is None:
            filter_names = sorted(existing_tables)
        else:
            filter_names = sorted(existing_tables.intersection(filter_names))
        relation_ids = [
            row["id"] for row in existing_relations
            if row["name"] in filter_names
        ]


        # Query
        # TODO: Refactor aka move to psycopg2, make _xxxx_query
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
    

    def get_multi_check_constraints(self, connection, table_name, schema=None, **kw):
        '''
        Materialize doesn't support constraint for tables built in Materialize.
        For other database like PostgreSQL, MySQL that is upstreamed to Materialize,
        you should connect directly to it with its corresponding SQLALchemy dialect
        '''
        return []  


    def get_multi_foreign_keys(
        self, connection, schema, filter_names, scope, kind, 
        postgresql_ignore_search_path=False, **kw
    ):
        '''
        Materialize doesn't support foreign key for tables built in Materialize.
        For other database like PostgreSQL, MySQL that is upstreamed to Materialize,
        you should connect directly to it with its corresponding SQLALchemy dialect
        '''
        return []
