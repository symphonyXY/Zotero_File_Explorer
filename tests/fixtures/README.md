# Fixture policy

Fixtures are created in tests/conftest.py and the isolated HTTP server in tests/integration/test_sync.py.
Temporary files live under build/pytest. They contain synthetic bytes, not Zotero documents.
No real Zotero database is opened, modified or bundled. The separate read-only live probe stores only
aggregate evidence and the two Glover attachment names explicitly supplied in the task.
