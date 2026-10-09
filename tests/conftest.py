import pytest


@pytest.fixture(autouse=True)
def inga_bildhamtningar(monkeypatch):
    """Testerna ska aldrig hämta bilder från nätet."""
    import bedomning
    monkeypatch.setattr(bedomning, "_forminska", lambda url: None)
    bedomning._BILDER.clear()
