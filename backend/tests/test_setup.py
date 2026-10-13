import pydantic

def test_setup_works():
    assert pydantic.VERSION.startswith("2")