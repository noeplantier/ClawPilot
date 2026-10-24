import uuid

import pytest

from db import url as dburl

PW = uuid.uuid4().hex  # generated per run: no credential-looking literal in the repository


@pytest.mark.parametrize(
    "given,expected",
    [
        ("postgres://{u}:{p}@h:5432/d", "postgresql+asyncpg://{u}:{p}@h:5432/d"),
        ("postgresql://{u}:{p}@h/d?sslmode=require", "postgresql+asyncpg://{u}:{p}@h/d?ssl=require"),
        ("postgresql+asyncpg://{u}:{p}@h/d", "postgresql+asyncpg://{u}:{p}@h/d"),
        (
            "postgresql://{u}:{p}@h/d?sslmode=verify-full&application_name=x",
            "postgresql+asyncpg://{u}:{p}@h/d?ssl=require&application_name=x",
        ),
    ],
)
def test_the_url_is_made_asyncpg_friendly(monkeypatch, given, expected):
    monkeypatch.setenv("DATABASE_URL", given.format(u="user", p=PW))
    assert dburl.async_database_url() == expected.format(u="user", p=PW)


@pytest.mark.parametrize(
    "host,port,kind",
    [
        ("aws-0-eu-west-3.pooler.supabase.com", 5432, "supabase_session_pooler"),
        ("aws-0-eu-west-3.pooler.supabase.com", 6543, "supabase_transaction_pooler"),
        ("db.abc.supabase.co", 5432, "supabase_direct"),
        ("dpg-abc", 5432, "render_postgres"),
        ("localhost", 5432, "local"),
    ],
)
def test_the_database_host_is_described_without_any_secret(monkeypatch, host, port, kind):
    monkeypatch.setenv("DATABASE_URL", f"postgresql://user:{PW}@{host}:{port}/postgres")
    info = dburl.describe_database()
    assert info["kind"] == kind and PW not in str(info)
