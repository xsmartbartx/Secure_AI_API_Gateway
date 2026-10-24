import os

# One event loop per test (pytest-asyncio), so pooled connections cannot be shared between tests. Set before the app is imported.
os.environ.setdefault("DB_DISABLE_POOL", "1")
