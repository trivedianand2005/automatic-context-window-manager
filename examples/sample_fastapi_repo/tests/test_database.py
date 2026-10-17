import pytest

from shopapi.core.config import Settings
from shopapi.core.errors import DatabaseUnavailableError
from shopapi.db.database import Database


def test_connect_succeeds_after_transient_failures():
    db = Database(Settings(database_url="flaky://2", db_max_retries=3, db_retry_base_delay=0))
    db.connect()
    assert db.connection_attempts == 3


def test_connect_gives_up_after_max_retries():
    db = Database(Settings(database_url="flaky://5", db_max_retries=3, db_retry_base_delay=0))
    with pytest.raises(DatabaseUnavailableError):
        db.connect()
    assert db.connection_attempts == 3
