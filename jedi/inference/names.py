from abc import abstractmethod
from inspect import Parameter
from typing import Optional, Tuple
from parso.tree import search_ancestor
from jedi.parser_utils import find_statement_documentation, clean_scope_docstring
from jedi.inference.utils import unite
from jedi.inference.base_value import ValueSet, NO_VALUES
from jedi.inference.cache import inference_state_method_cache
from jedi.inference import docstrings
from jedi.cache import memoize_method
from jedi.inference.helpers import deep_ast_copy, infer_call_of_leaf
from jedi.plugins import plugin_manager

class AbstractNameDefinition:
    start_pos: Optional[Tuple[int, int]] = None
    string_name: str
    parent_context = None
    tree_name = None
    is_value_name = True
    "\n    Used for the Jedi API to know if it's a keyword or an actual name.\n    "

    def __repr__(self):
        if self.start_pos is None:
            return '<%s: string_name=%s>' % (self.__class__.__name__, self.string_name)
        return '<%s: string_name=%s start_pos=%s>' % (self.__class__.__name__, self.string_name, self.start_pos)

    def get_defining_qualified_value(self):
        """
        Returns either None or the value that is public and qualified. Won't
        return a function, because a name in a function is never public.
        """
        if self.parent_context and not self.parent_context.is_function():
            return self.parent_context.get_value()
        return None

class AbstractArbitraryName(AbstractNameDefinition):
    """
    When you e.g. want to complete dicts keys, you probably want to complete
    string literals, which is not really a name, but for Jedi we use this
    concept of Name for completions as well.
    """
    is_value_name = False

    def __init__(self, inference_state, string):
        self.inference_state = inference_state
        self.string_name = string
        self.parent_context = inference_state.builtins_module
        self.start_pos = None  # AbstractArbitraryName doesn't have a start position

class AbstractTreeName(AbstractNameDefinition):

    def __init__(self, parent_context, tree_name):
        self.parent_context = parent_context
        self.tree_name = tree_name

class ValueNameMixin:
    pass

class ValueName(ValueNameMixin, AbstractTreeName):

    def __init__(self, value, tree_name):
        super().__init__(value.parent_context, tree_name)
        self._value = value

class TreeNameDefinition(AbstractTreeName):
    _API_TYPES = dict(import_name='module', import_from='module', funcdef='function', param='param', classdef='class')

    def assignment_indexes(self):
        """
        Returns an array of tuple(int, node) of the indexes that are used in
        tuple assignments.

        For example if the name is ``y`` in the following code::

            x, (y, z) = 2, ''

        would result in ``[(1, xyz_node), (0, yz_node)]``.

        When searching for b in the case ``a, *b, c = [...]`` it will return::

            [(slice(1, -1), abc_node)]
        """
        indexes = []
        node = self.tree_name.parent
        while node is not None:
            if node.type == 'testlist_star_expr' or node.type == 'exprlist':
                for i, child in enumerate(node.children):
                    if child == self.tree_name:
                        indexes.insert(0, (i, node))
                    elif child.type == 'atom' and self.tree_name in child.children:
                        indexes.insert(0, (i, node))
                        indexes.insert(0, (child.children.index(self.tree_name), child))
            elif node.type == 'atom' and node.children[0] == '[' and node.children[-1] == ']':
                star_count = sum(1 for c in node.children if c.type == 'star_expr')
                if star_count == 1:
                    for i, child in enumerate(node.children):
                        if child.type == 'star_expr' and self.tree_name in child.children:
                            indexes.insert(0, (slice(i, -star_count), node))
                            break
            node = node.parent
        return indexes

class _ParamMixin:
    pass

class ParamNameInterface(_ParamMixin):
    api_type = 'param'

    def get_executed_param_name(self):
        """
        For dealing with type inference and working around the graph, we
        sometimes want to have the param name of the execution. This feels a
        bit strange and we might have to refactor at some point.

        For now however it exists to avoid infering params when we don't really
        need them (e.g. when we can just instead use annotations.
        """
        return self

class BaseTreeParamName(ParamNameInterface, AbstractTreeName):
    annotation_node = None
    default_node = None

class _ActualTreeParamName(BaseTreeParamName):

    def __init__(self, function_value, tree_name):
        super().__init__(function_value.get_default_param_context(), tree_name)
        self.function_value = function_value

class AnonymousParamName(_ActualTreeParamName):
    pass

class ParamName(_ActualTreeParamName):

    def __init__(self, function_value, tree_name, arguments):
        super().__init__(function_value, tree_name)
        self.arguments = arguments

class ParamNameWrapper(_ParamMixin):

    def __init__(self, param_name):
        self._wrapped_param_name = param_name

    def __getattr__(self, name):
        return getattr(self._wrapped_param_name, name)

    def __repr__(self):
        return '<%s: %s>' % (self.__class__.__name__, self._wrapped_param_name)

class ImportName(AbstractNameDefinition):
    start_pos = (1, 0)
    _level = 0

    def __init__(self, parent_context, string_name):
        self._from_module_context = parent_context
        self.string_name = string_name
        self.parent_context = parent_context

class SubModuleName(ImportName):
    _level = 1

class NameWrapper:

    def __init__(self, wrapped_name):
        self._wrapped_name = wrapped_name

    def __getattr__(self, name):
        return getattr(self._wrapped_name, name)

    def __repr__(self):
        return f'{self.__class__.__name__}({self._wrapped_name!r})'

class StubNameMixin:
    pass

class StubName(StubNameMixin, TreeNameDefinition):
    pass

class ModuleName(ValueNameMixin, AbstractNameDefinition):
    start_pos = (1, 0)

    def __init__(self, value, name):
        self._value = value
        self._name = name
        self.string_name = name
        self.parent_context = value.as_context()

class StubModuleName(StubNameMixin, ModuleName):
    pass
