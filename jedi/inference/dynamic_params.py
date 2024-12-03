"""
One of the really important features of |jedi| is to have an option to
understand code like this::

    def foo(bar):
        bar. # completion here
    foo(1)

There's no doubt wheter bar is an ``int`` or not, but if there's also a call
like ``foo('str')``, what would happen? Well, we'll just show both. Because
that's what a human would expect.

It works as follows:

- |Jedi| sees a param
- search for function calls named ``foo``
- execute these calls and check the input.
"""
from jedi import settings
from jedi import debug
from jedi.parser_utils import get_parent_scope
from jedi.inference.cache import inference_state_method_cache
from jedi.inference.arguments import TreeArguments
from jedi.inference.param import get_executed_param_names
from jedi.inference.helpers import is_stdlib_path
from jedi.inference.utils import to_list
from jedi.inference.value import instance
from jedi.inference.base_value import ValueSet, NO_VALUES
from jedi.inference.references import get_module_contexts_containing_name
from jedi.inference import recursion
MAX_PARAM_SEARCHES = 20

@debug.increase_indent
@_avoid_recursions
def dynamic_param_lookup(function_value, param_index):
    """
    A dynamic search for param values. If you try to complete a type:

    >>> def func(foo):
    ...     foo
    >>> func(1)
    >>> func("")

    It is not known what the type ``foo`` without analysing the whole code. You
    have to look for all calls to ``func`` to find out what ``foo`` possibly
    is.
    """
    debug.dbg('Dynamic param lookup for %s param %i', function_value, param_index)
    module_context = function_value.get_root_context()
    function_executions = _search_function_arguments(module_context, function_value.tree_node, function_value.name.string_name)
    values = NO_VALUES
    for name, value in function_executions:
        if name.get_param_index() == param_index:
            values |= value.infer()
    return values

@inference_state_method_cache(default=None)
@to_list
def _search_function_arguments(module_context, funcdef, string_name):
    """
    Returns a list of param names.
    """
    try:
        executions = get_module_contexts_containing_name(
            module_context.inference_state,
            [module_context],
            string_name
        )
    except KeyError:
        # If a KeyError is raised, it means the function name was not found
        # in any module, so we return an empty list.
        return []

    result = []
    for execution in executions:
        tree_node = execution.tree_node
        for name, trailer in _get_possible_nodes(tree_node):
            if name.value == string_name:
                arguments = TreeArguments(module_context.inference_state, execution, trailer)
                result += arguments.unpack()
    return result

def _get_possible_nodes(node):
    for child in node.children:
        if child.type == 'name':
            trailer = child.get_next_sibling()
            if trailer is not None and trailer.type == 'trailer' and trailer.children[0] == '(':
                yield child, trailer
        else:
            yield from _get_possible_nodes(child)
