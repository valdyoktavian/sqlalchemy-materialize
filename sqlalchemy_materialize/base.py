# sqlalchemy_materialize/base.py
from sqlalchemy.dialects.postgresql.base import PGDialect


class MaterializeDialect(PGDialect):
    name = "materialize"
    supports_statement_cache = False


    # Handled in base.py
    # TODO: Refactor base.py so that the query is cooked here.
    
    # def _columns_query(self, schema, has_filter_names, scope, kind):
    #     '''
    #     Returns: A SQLAlchemy Select yielding column name, type, default, nullability, table name, comment, generated/identity options, and collation.

    #     Replace pg_attrdef, pg_sequence, pg_get_serial_sequence, and pg_collation_is_visible dependencies.

    #     PostgreSQL reference:
    #     https://github.com/sqlalchemy/sqlalchemy/blob/main/lib/sqlalchemy/dialects/postgresql/base.py
    #     '''

    # def _pg_opclass_notdefault_query(self):
    #     '''
    #     Returns: A SQLAlchemy Select yielding (oid, opcname) for non-default operator classes.

    #     Replace the unsupported pg_opclass lookup; upstream uses a memoized property.

    #     PostgreSQL reference:
    #     https://github.com/sqlalchemy/sqlalchemy/blob/main/lib/sqlalchemy/dialects/postgresql/base.py
    #     '''

    # def _domain_query(self, schema):
    #     '''
    #     Returns: A SQLAlchemy Select yielding domain name, base type, nullability, default, visibility, schema, constraints, and collation metadata.

    #     Replace pg_collation_is_visible and account for the pg_get_constraintdef NULL shim.

    #     PostgreSQL reference:
    #     https://github.com/sqlalchemy/sqlalchemy/blob/main/lib/sqlalchemy/dialects/postgresql/base.py
    #     '''

    # def _foreing_key_query(self, schema, has_filter_names, scope, kind):
    #     '''
    #     Returns: A SQLAlchemy Select yielding table name, constraint name, constraint definition, referenced schema, and comment.

    #     Account for pg_get_constraintdef returning NULL; upstream spells this method _foreing_key_query.

    #     PostgreSQL reference:
    #     https://github.com/sqlalchemy/sqlalchemy/blob/main/lib/sqlalchemy/dialects/postgresql/base.py
    #     '''

    # def _check_constraint_query(self, schema, has_filter_names, scope, kind):
    #     '''
    #     Returns: A SQLAlchemy Select yielding table name, constraint name, constraint definition, and comment.

    #     Account for pg_get_constraintdef returning NULL.

    #     PostgreSQL reference:
    #     https://github.com/sqlalchemy/sqlalchemy/blob/main/lib/sqlalchemy/dialects/postgresql/base.py
    #     '''

    def do_recover_twophase(self, connection):
        '''
        Materialize does not support two-phase commit recovery
        '''
        
        raise NotImplementedError(
            "Materialize does not support two-phase commit recovery"
        )
