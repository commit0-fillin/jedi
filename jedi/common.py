from contextlib import contextmanager

@contextmanager
def monkeypatch(obj, attribute_name, new_value):
    """
    Like pytest's monkeypatch, but as a value manager.
    """
    original_value = getattr(obj, attribute_name)
    setattr(obj, attribute_name, new_value)
    try:
        yield
    finally:
        setattr(obj, attribute_name, original_value)

def indent_block(text, indention='    '):
    """This function indents a text block with a default of four spaces."""
    return '\n'.join(indention + line for line in text.splitlines())
