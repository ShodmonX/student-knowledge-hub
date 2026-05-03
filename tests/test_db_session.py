import pytest

from app.db import session as db_session_module


@pytest.mark.asyncio
async def test_get_db_session_rolls_back_active_transaction_on_error(monkeypatch):
    class FakeSession:
        rolled_back = False

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

        def in_transaction(self):
            return True

        async def rollback(self):
            self.rolled_back = True

    fake_session = FakeSession()
    monkeypatch.setattr(db_session_module, "AsyncSessionLocal", lambda: fake_session)

    generator = db_session_module.get_db_session()
    yielded = await generator.__anext__()
    assert yielded is fake_session

    with pytest.raises(RuntimeError, match="session failure"):
        await generator.athrow(RuntimeError("session failure"))

    assert fake_session.rolled_back is True
