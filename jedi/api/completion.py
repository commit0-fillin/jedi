import re
from textwrap import dedent
from inspect import Parameter
from parso.python.token import PythonTokenTypes
from parso.python import tree
from parso.tree import search_ancestor, Leaf
from parso import split_lines
from jedi import debug
from jedi import settings
from jedi.api import classes
from jedi.api import helpers
from jedi.api import keywords
from jedi.api.strings import complete_dict
from jedi.api.file_name import complete_file_name
from jedi.inference import imports
from jedi.inference.base_value import ValueSet
from jedi.inference.helpers import infer_call_of_leaf, parse_dotted_names
from jedi.inference.context import get_global_filters
from jedi.inference.value import TreeInstance
from jedi.inference.docstring_utils import DocstringModule
from jedi.inference.names import ParamNameWrapper, SubModuleName
from jedi.inference.gradual.conversion import convert_values, convert_names
from jedi.parser_utils import cut_value_at_position
from jedi.plugins import plugin_manager

class ParamNameWithEquals(ParamNameWrapper):
    pass

def get_user_context(module_context, position):
    """
    Returns the scope in which the user resides. This includes flows.
    """
    leaf = module_context.tree_node.get_leaf_for_position(position)
    if leaf is None:
        return None

    parent_scope = get_parent_scope(leaf)
    if parent_scope is None:
        return module_context

    return module_context.create_context(parent_scope)

class Completion:

    def __init__(self, inference_state, module_context, code_lines, position, signatures_callback, fuzzy=False):
        self._inference_state = inference_state
        self._module_context = module_context
        self._module_node = module_context.tree_node
        self._code_lines = code_lines
        self._like_name = helpers.get_on_completion_name(self._module_node, code_lines, position)
        self._original_position = position
        self._signatures_callback = signatures_callback
        self._fuzzy = fuzzy

    def _complete_python(self, leaf):
        """
        Analyzes the current context of a completion and decides what to
        return.

        Technically this works by generating a parser stack and analysing the
        current stack for possible grammar nodes.

        Possible enhancements:
        - global/nonlocal search global
        - yield from / raise from <- could be only exceptions/generators
        - In args: */**: no completion
        - In params (also lambda): no completion before =
        """
        user_context = get_user_context(self._module_context, self._original_position)
        if user_context is None:
            return []

        parser_stack = get_stack_at_position(
            self._inference_state.grammar,
            self._code_lines,
            leaf,
            self._original_position
        )

        completion_names = []
        for stack_node in reversed(parser_stack):
            if stack_node in ['import_stmt', 'import_from']:
                completion_names = self._complete_import(leaf)
                break
            elif stack_node == 'trailer':
                completion_names = self._complete_trailer(leaf)
                break
            elif stack_node in ['atom_expr', 'power']:
                completion_names = self._complete_power(leaf)
                break

        if not completion_names:
            completion_names = self._complete_global_scope(leaf)

        return completion_names

    def _complete_inherited(self, is_function=True):
        """
        Autocomplete inherited methods when overriding in child class.
        """
        leaf = self._module_node.get_leaf_for_position(self._original_position)
        cls = search_ancestor(leaf, 'classdef')
        if cls is None:
            return []

        class_value = self._module_context.create_value(cls)
        if not class_value.is_class():
            return []

        names = []
        for base in class_value.py__bases__():
            if is_function:
                names.extend(base.get_function_names())
            else:
                names.extend(base.get_property_names())

        return [Completion(self._inference_state, n, stack=None, like_name_length=0, is_fuzzy=False)
                for n in names]

    def _complete_in_string(self, start_leaf, string):
        """
        To make it possible for people to have completions in doctests or
        generally in "Python" code in docstrings, we use the following
        heuristic:

        - Having an indented block of code
        - Having some doctest code that starts with `>>>`
        - Having backticks that doesn't have whitespace inside it
        """
        match = _string_start.match(string)
        if match is None:
            return []

        string = string[match.end():]
        lines = string.splitlines()
        if not lines:
            return []

        if lines[-1].startswith('>>>'):
            # Doctest
            code = '\n'.join(lines)
        elif len(lines) > 1 and lines[0].strip() and not lines[0].lstrip().startswith('>>>'):
            # Indented block of code
            code = textwrap.dedent('\n'.join(lines))
        else:
            # Try to find backticks that don't contain a space
            for line in lines:
                match = re.search(r'`([^`\s]+`)', line)
                if match is not None:
                    code = match.group(1)
                    break
            else:
                return []

        module = self._inference_state.parse(code)
        module_context = self._module_context.create_context(module)
        return self._complete_python(module.get_last_leaf())
_string_start = re.compile('^\\w*(\\\'{3}|"{3}|\\\'|")')

def _complete_getattr(user_context, instance):
    """
    A heuristic to make completion for proxy objects work. This is not
    intended to work in all cases. It works exactly in this case:

        def __getattr__(self, name):
            ...
            return getattr(any_object, name)

    It is important that the return contains getattr directly, otherwise it
    won't work anymore. It's really just a stupid heuristic. It will not
    work if you write e.g. `return (getatr(o, name))`, because of the
    additional parentheses. It will also not work if you move the getattr
    to some other place that is not the return statement itself.

    It is intentional that it doesn't work in all cases. Generally it's
    really hard to do even this case (as you can see below). Most people
    will write it like this anyway and the other ones, well they are just
    out of luck I guess :) ~dave.
    """
    name_context = instance.get_function_slot_names(u'__getattr__')
    if not name_context:
        return NO_VALUES

    return_stmt = name_context[0].tree_name.get_definition().get_return_stmt()
    if return_stmt is None:
        return NO_VALUES

    getattr_call = return_stmt.get_rhs()
    if not isinstance(getattr_call, tree.Name) or getattr_call.value != 'getattr':
        return NO_VALUES

    arguments = getattr_call.get_next_sibling()
    if arguments is None or arguments.type != 'trailer' or len(arguments.children) != 3:
        return NO_VALUES

    # Now we need to get the first argument
    first_arg = arguments.children[1].children[0]
    return user_context.infer_node(first_arg)
