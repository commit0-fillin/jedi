"""
Docstrings are another source of information for functions and classes.
:mod:`jedi.inference.dynamic_params` tries to find all executions of functions,
while the docstring parsing is much easier. There are three different types of
docstrings that |jedi| understands:

- `Sphinx <http://sphinx-doc.org/markup/desc.html#info-field-lists>`_
- `Epydoc <http://epydoc.sourceforge.net/manual-fields.html>`_
- `Numpydoc <https://github.com/numpy/numpy/blob/master/doc/HOWTO_DOCUMENT.rst.txt>`_

For example, the sphinx annotation ``:type foo: str`` clearly states that the
type of ``foo`` is ``str``.

As an addition to parameter searching, this module also provides return
annotations.
"""
import re
import warnings
from parso import parse, ParserSyntaxError
from jedi import debug
from jedi.inference.cache import inference_state_method_cache
from jedi.inference.base_value import iterator_to_value_set, ValueSet, NO_VALUES
from jedi.inference.lazy_value import LazyKnownValues
DOCSTRING_PARAM_PATTERNS = ['\\s*:type\\s+%s:\\s*([^\\n]+)', '\\s*:param\\s+(\\w+)\\s+%s:[^\\n]*', '\\s*@type\\s+%s:\\s*([^\\n]+)']
DOCSTRING_RETURN_PATTERNS = [re.compile('\\s*:rtype:\\s*([^\\n]+)', re.M), re.compile('\\s*@rtype:\\s*([^\\n]+)', re.M)]
REST_ROLE_PATTERN = re.compile(':[^`]+:`([^`]+)`')
_numpy_doc_string_cache = None

def _search_param_in_numpydocstr(docstr, param_str):
    """Search `docstr` (in numpydoc format) for type(-s) of `param_str`."""
    import re
    pattern = rf'^{re.escape(param_str)}\s*:\s*(.*?)$'
    match = re.search(pattern, docstr, re.MULTILINE)
    if match:
        type_str = match.group(1).strip()
        return _expand_typestr(type_str)
    return []

def _search_return_in_numpydocstr(docstr):
    """
    Search `docstr` (in numpydoc format) for type(-s) of function returns.
    """
    import re
    pattern = r'^Returns\n.*?-+\n(.*?)(\n\n|\Z)'
    match = re.search(pattern, docstr, re.MULTILINE | re.DOTALL)
    if match:
        return_block = match.group(1)
        type_pattern = r'(?:^|\n)(.+?)\s*:'
        types = re.findall(type_pattern, return_block)
        return [_expand_typestr(t.strip()) for t in types]
    return []

def _expand_typestr(type_str):
    """
    Attempts to interpret the possible types in `type_str`
    """
    import re
    types = []
    for match in re.finditer(r'([^,\s\[]+)(?:\[([^\]]+)\])?', type_str):
        main_type, sub_type = match.groups()
        if main_type.lower() == 'or':
            continue
        if sub_type:
            types.append(f"{main_type}[{sub_type}]")
        else:
            types.append(main_type)
    return types

def _search_param_in_docstr(docstr, param_str):
    """
    Search `docstr` for type(-s) of `param_str`.

    >>> _search_param_in_docstr(':type param: int', 'param')
    ['int']
    >>> _search_param_in_docstr('@type param: int', 'param')
    ['int']
    >>> _search_param_in_docstr(
    ...   ':type param: :class:`threading.Thread`', 'param')
    ['threading.Thread']
    >>> bool(_search_param_in_docstr('no document', 'param'))
    False
    >>> _search_param_in_docstr(':param int param: some description', 'param')
    ['int']

    """
    import re
    patterns = [
        rf':type\s+{re.escape(param_str)}:\s*([^\n]+)',
        rf'@type\s+{re.escape(param_str)}:\s*([^\n]+)',
        rf':param\s+([^:]+)\s+{re.escape(param_str)}:[^\n]*',
    ]
    for pattern in patterns:
        match = re.search(pattern, docstr)
        if match:
            return _expand_typestr(_strip_rst_role(match.group(1)))
    return []

def _strip_rst_role(type_str):
    """
    Strip off the part looks like a ReST role in `type_str`.

    >>> _strip_rst_role(':class:`ClassName`')  # strip off :class:
    'ClassName'
    >>> _strip_rst_role(':py:obj:`module.Object`')  # works with domain
    'module.Object'
    >>> _strip_rst_role('ClassName')  # do nothing when not ReST role
    'ClassName'

    See also:
    http://sphinx-doc.org/domains.html#cross-referencing-python-objects

    """
    import re
    match = re.match(r':[^`]+:`(.+)`', type_str)
    if match:
        return match.group(1)
    return type_str

def _execute_types_in_stmt(module_context, stmt):
    """
    Executing all types or general elements that we find in a statement. This
    doesn't include tuple, list and dict literals, because the stuff they
    contain is executed. (Used as type information).
    """
    from jedi.inference.value import TreeInstance
    from jedi.inference.gradual.annotation import AnnotatedAnnassign
    from jedi.inference.gradual.base import GenericClass

    definitions = module_context.infer_node(stmt)
    return ValueSet(
        instance
        for instance in definitions
        if isinstance(instance, (TreeInstance, GenericClass, AnnotatedAnnassign))
    )

def _execute_array_values(inference_state, array):
    """
    Tuples indicate that there's not just one return value, but the listed
    ones.  `(str, int)` means that it returns a tuple with both types.
    """
    from jedi.inference.value.iterable import SequenceLiteralValue, FakeTuple
    from jedi.inference.base_value import ValueSet, NO_VALUES

    if isinstance(array, SequenceLiteralValue):
        values = ValueSet.from_sets(
            _execute_array_values(inference_state, v)
            for v in array.py__iter__()
        )
        return ValueSet([FakeTuple(inference_state, values)])
    elif isinstance(array, (FakeTuple, SequenceLiteralValue)):
        return ValueSet([array])
    else:
        return inference_state.infer(array)
