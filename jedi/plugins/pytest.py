import sys
from typing import List
from pathlib import Path
from parso.tree import search_ancestor
from jedi.inference.cache import inference_state_method_cache
from jedi.inference.imports import goto_import, load_module_from_path
from jedi.inference.filters import ParserTreeFilter
from jedi.inference.base_value import NO_VALUES, ValueSet
from jedi.inference.helpers import infer_call_of_leaf
_PYTEST_FIXTURE_MODULES = [('_pytest', 'monkeypatch'), ('_pytest', 'capture'), ('_pytest', 'logging'), ('_pytest', 'tmpdir'), ('_pytest', 'pytester')]

def _is_a_pytest_param_and_inherited(param_name):
    """
    Pytest params are either in a `test_*` function or have a pytest fixture
    with the decorator @pytest.fixture.

    This is a heuristic and will work in most cases.
    """
    def is_pytest_param(node):
        if node.type == 'funcdef':
            # Check if it's a test function
            if node.name.value.startswith('test_'):
                return True
            # Check for pytest.fixture decorator
            for decorator in node.get_decorators():
                if decorator.children[1].value == 'pytest' and decorator.children[3].value == 'fixture':
                    return True
        return False

    parent = param_name.parent
    while parent:
        if is_pytest_param(parent):
            return True
        parent = parent.parent
    return False

def _find_pytest_plugin_modules() -> List[List[str]]:
    """
    Finds pytest plugin modules hooked by setuptools entry points

    See https://docs.pytest.org/en/stable/how-to/writing_plugins.html#setuptools-entry-points
    """
    try:
        import pkg_resources
    except ImportError:
        return []

    plugin_modules = []
    for entry_point in pkg_resources.iter_entry_points('pytest11'):
        try:
            module_name = entry_point.module_name
            if module_name:
                plugin_modules.append(module_name.split('.'))
        except Exception:
            # Skip any entry points that cause errors
            continue

    return plugin_modules

class FixtureFilter(ParserTreeFilter):
    pass
