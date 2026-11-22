from sqlalchemy.dialects.postgresql.base import PGDialect


class MaterializeDialect(PGDialect):
    name = "materialize"
    supports_statement_cache = False


    def do_recover_twophase(self, connection):
        '''
        Materialize does not support two-phase commit recovery
        '''
        
        raise NotImplementedError(
            "Materialize does not support two-phase commit recovery"
        )
