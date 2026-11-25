from django.db import connections
from django.test.runner import DiscoverRunner

KILL_SESSIONS = (
    'SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()'
)


class PoolerSafeRunner(DiscoverRunner):
    """The Supabase session pooler keeps sessions open on the test database (and reopens them after a kill),
    so Django cannot drop it. Stop new connections, then disconnect the old ones, before Django drops it.
    The database is dropped right after, so ALLOW_CONNECTIONS is never left off on a database we keep."""

    @staticmethod
    def _release(connection, test_name: str) -> None:
        connection.close()
        with connection._nodb_cursor() as cursor:
            cursor.execute('SELECT 1 FROM pg_database WHERE datname = %s', [test_name])
            if cursor.fetchone():
                cursor.execute(f'ALTER DATABASE {connection.ops.quote_name(test_name)} WITH ALLOW_CONNECTIONS false')
                cursor.execute(KILL_SESSIONS, [test_name])

    @staticmethod
    def _reopen(connection, test_name: str) -> None:
        with connection._nodb_cursor() as cursor:
            cursor.execute('SELECT 1 FROM pg_database WHERE datname = %s', [test_name])
            if cursor.fetchone():
                cursor.execute(f'ALTER DATABASE {connection.ops.quote_name(test_name)} WITH ALLOW_CONNECTIONS true')

    def setup_databases(self, **kwargs):
        if self.keepdb:
            return super().setup_databases(**kwargs)
        names = [(connection, connection.creation._get_test_db_name()) for connection in connections.all()]
        for connection, test_name in names:
            self._release(connection, test_name)
        try:
            return super().setup_databases(**kwargs)
        except BaseException:
            # "no" at Django's delete prompt or Ctrl+C keeps the old DB: don't leave it locked for --keepdb runs.
            for connection, test_name in names:
                self._reopen(connection, test_name)
            raise

    def teardown_databases(self, old_config, **kwargs) -> None:
        if not self.keepdb:
            for connection, _, _ in old_config:
                self._release(connection, connection.settings_dict['NAME'])  # already the test name here
        super().teardown_databases(old_config, **kwargs)
