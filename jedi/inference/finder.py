"""
Searching for names with given scope and name. This is very central in Jedi and
Python. The name resolution is quite complicated with descripter,
``__getattribute__``, ``__getattr__``, ``global``, etc.

If you want to understand name resolution, please read the first few chapters
in http://blog.ionelmc.ro/2015/02/09/understanding-python-metaclasses/.

Flow checks
+++++++++++

Flow checks are not really mature. There's only a check for ``isinstance``.  It
would check whether a flow has the form of ``if isinstance(a, type_or_tuple)``.
Unfortunately every other thing is being ignored (e.g. a == '' would be easy to
check for -> a is a string). There's big potential in these checks.
"""
from parso.tree import search_ancestor
from parso.python.tree import Name
from jedi import settings
from jedi.inference.arguments import TreeArguments
from jedi.inference.value import iterable
from jedi.inference.base_value import NO_VALUES
from jedi.parser_utils import is_scope

def filter_name(filters, name_or_str):
    """
    Searches names that are defined in a scope (the different
    ``filters``), until a name fits.
    """
    string_name = name_or_str.value if isinstance(name_or_str, tree.Name) else name_or_str
    for filter in filters:
        names = filter.get(string_name)
        if names:
            return names
    return []

def check_flow_information(value, flow, search_name, pos):
    """ Try to find out the type of a variable just with the information that
    is given by the flows: e.g. It is also responsible for assert checks.::

        if isinstance(k, str):
            k.  # <- completion here

    ensures that `k` is a string.
    """
    if flow is None:
        return None

    if flow.type in ('if_stmt', 'while_stmt'):
        potential_node = flow.children[1]
        if potential_node != 'COLON':
            if search_name in potential_node.get_defined_names():
                return _check_isinstance_type(flow, search_name, value)

    return None

def _check_isinstance_type(flow, search_name, value):
    try:
        assert flow.type in ('if_stmt', 'while_stmt')
        assert flow.children[0] == 'if'
        assert flow.children[1].type == 'power'
        assert flow.children[1].children[0].value == 'isinstance'
        call = flow.children[1].children[1]
        assert call.type == 'trailer'
        assert call.children[0] == '('
        params = call.children[1].children
        assert len(params) == 3
        assert params[0].value == search_name
        assert params[1] == ','
        classes = params[2]
    except AssertionError:
        return None

    if classes.type == 'atom':
        return _create_isinstance_value(value.inference_state, classes)
    return None

def _create_isinstance_value(inference_state, classes):
    if classes.type == 'name':
        return ValueSet([inference_state.builtins_module.py__getattribute__(classes.value)])
    elif classes.type == 'atom' and classes.children[0] == '(':
        # It's a tuple.
        types = ValueSet()
        for name in classes.children[1].children[::2]:
            types |= ValueSet([inference_state.builtins_module.py__getattribute__(name.value)])
        return types
    return None
