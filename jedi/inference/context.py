from abc import abstractmethod
from contextlib import contextmanager
from pathlib import Path
from typing import Optional
from parso.tree import search_ancestor
from parso.python.tree import Name
from jedi.inference.filters import ParserTreeFilter, MergedFilter, GlobalNameFilter
from jedi.inference.names import AnonymousParamName, TreeNameDefinition
from jedi.inference.base_value import NO_VALUES, ValueSet
from jedi.parser_utils import get_parent_scope
from jedi import debug
from jedi import parser_utils

class AbstractContext:

    def __init__(self, inference_state):
        self.inference_state = inference_state
        self.predefined_names = {}

    def py__getattribute__(self, name_or_str, name_context=None, position=None, analysis_errors=True):
        """
        :param position: Position of the last statement -> tuple of line, column
        """
        if isinstance(name_or_str, str):
            name = name_or_str
        else:
            name = name_or_str.value

        if name in self.predefined_names:
            return self.predefined_names[name]

        return NO_VALUES

class ValueContext(AbstractContext):
    """
    Should be defined, otherwise the API returns empty types.
    """

    def __init__(self, value):
        super().__init__(value.inference_state)
        self._value = value

    def __repr__(self):
        return f'{self.__class__.__name__}({self._value!r})'

class TreeContextMixin:
    pass

class FunctionContext(TreeContextMixin, ValueContext):
    pass

class ModuleContext(TreeContextMixin, ValueContext):

    def get_value(self):
        """
        This is the only function that converts a context back to a value.
        This is necessary for stub -> python conversion and vice versa. However
        this method shouldn't be moved to AbstractContext.
        """
        return self._value

class NamespaceContext(TreeContextMixin, ValueContext):
    pass

class ClassContext(TreeContextMixin, ValueContext):
    pass

class CompForContext(TreeContextMixin, AbstractContext):

    def __init__(self, parent_context, comp_for):
        super().__init__(parent_context.inference_state)
        self.tree_node = comp_for
        self.parent_context = parent_context

    def __repr__(self):
        return f'{self.__class__.__name__}({self.tree_node!r})'

class CompiledContext(ValueContext):
    pass

class CompiledModuleContext(CompiledContext):
    code_lines = None

def get_global_filters(context, until_position, origin_scope):
    """
    Returns all filters in order of priority for name resolution.

    For global name lookups. The filters will handle name resolution
    themselves, but here we gather possible filters downwards.

    >>> from jedi import Script
    >>> script = Script('''
    ... x = ['a', 'b', 'c']
    ... def func():
    ...     y = None
    ... ''')
    >>> module_node = script._module_node
    >>> scope = next(module_node.iter_funcdefs())
    >>> scope
    <Function: func@3-5>
    >>> context = script._get_module_context().create_context(scope)
    >>> filters = list(get_global_filters(context, (4, 0), None))

    First we get the names from the function scope.

    >>> print(filters[0])  # doctest: +ELLIPSIS
    MergedFilter(<ParserTreeFilter: ...>, <GlobalNameFilter: ...>)
    >>> sorted(str(n) for n in filters[0].values())  # doctest: +NORMALIZE_WHITESPACE
    ['<TreeNameDefinition: string_name=func start_pos=(3, 4)>',
     '<TreeNameDefinition: string_name=x start_pos=(2, 0)>']
    >>> filters[0]._filters[0]._until_position
    (4, 0)
    >>> filters[0]._filters[1]._until_position

    Then it yields the names from one level "lower". In this example, this is
    the module scope (including globals).
    As a side note, you can see, that the position in the filter is None on the
    globals filter, because there the whole module is searched.

    >>> list(filters[1].values())  # package modules -> Also empty.
    []
    >>> sorted(name.string_name for name in filters[2].values())  # Module attributes
    ['__doc__', '__name__', '__package__']

    Finally, it yields the builtin filter, if `include_builtin` is
    true (default).

    >>> list(filters[3].values())  # doctest: +ELLIPSIS
    [...]
    """
    def yield_filters():
        while context is not None:
            if isinstance(context, FunctionContext):
                yield MergedFilter(
                    ParserTreeFilter(
                        context,
                        until_position=until_position,
                        origin_scope=origin_scope
                    ),
                    GlobalNameFilter(context),
                )
            elif isinstance(context, ClassContext):
                yield ParserTreeFilter(
                    context,
                    until_position=until_position,
                    origin_scope=origin_scope
                )
            elif isinstance(context, ModuleContext):
                yield MergedFilter(
                    ParserTreeFilter(
                        context,
                        until_position=until_position,
                        origin_scope=origin_scope
                    ),
                    GlobalNameFilter(context),
                )
                yield context.inference_state.builtins_module.as_context().get_global_filter()
            context = context.parent_context

    yield from yield_filters()
