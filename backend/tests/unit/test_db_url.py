import pytest

from db import url as dburl


@pytest.mark.parametrize(
    "given,expected",
    [
        ("postgres://u:p@h:5432/d", "postgresql+asyncpg://u:p@h:5432/d"),
        ("postgresql://u:p@h/d?sslmode=require", "postgresql+asyncpg://u:p@h/d?ssl=require"),
        ("postgresql+asyncpg://u:p@h/d", "postgresql+asyncpg://u:p@h/d"),
        (
            "postgresql://u:p@h/d?sslmode=verify-full&application_name=x",
            "postgresql+asyncpg://u:p@h/d?ssl=require&application_name=x",
        ),
    ],
)
def test_the_url_is_made_asyncpg_friendly(monkeypatch, given, expected):
    monkeypatch.setenv("DATABASE_URL", given)
    assert dburl.async_database_url() == expected


@pytest.mark.parametrize(
    "given,kind",
    [
        (
            "postgresql://postgres.abc:secret@aws-0-eu-west-3.pooler.supabase.com:5432/postgres",
            "supabase_session_pooler",
        ),
        (
            "postgresql://postgres.abc:secret@aws-0-eu-west-3.pooler.supabase.com:6543/postgres",
            "supabase_transaction_pooler",
        ),
        ("postgresql://postgres:secret@db.abc.supabase.co:5432/postgres", "supabase_direct"),
        ("postgresql://u:p@dpg-abc/d", "render_postgres"),
        ("postgresql://u:p@localhost:5432/d", "local"),
    ],
)
def test_the_database_host_is_described_without_any_secret(monkeypatch, given, kind):
    monkeypatch.setenv("DATABASE_URL", given)
    info = dburl.describe_database()
    assert info["kind"] == kind and "secret" not in str(info)
