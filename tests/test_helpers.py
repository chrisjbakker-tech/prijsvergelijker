from app.main import euros_to_cents, valid_email, valid_url


def test_euros_to_cents():
    assert euros_to_cents("140,00") == 14000
    assert euros_to_cents("") is None


def test_validation():
    assert valid_email("chris@example.nl")
    assert not valid_email("geen-adres")
    assert valid_url("https://example.nl/product")
    assert not valid_url("javascript:alert(1)")
