"""
We need to somehow work with the typing objects. Since the typing objects are
pretty bare we need to add all the Jedi customizations to make them work as
values.

This file deals with all the typing.py cases.
"""
import itertools
from jedi import debug
from jedi.inference.compiled import builtin_from_name, create_simple_object
from jedi.inference.base_value import ValueSet, NO_VALUES, Value, LazyValueWrapper, ValueWrapper
from jedi.inference.lazy_value import LazyKnownValues
from jedi.inference.arguments import repack_with_argument_clinic
from jedi.inference.filters import FilterWrapper
from jedi.inference.names import NameWrapper, ValueName
from jedi.inference.value.klass import ClassMixin
from jedi.inference.gradual.base import BaseTypingValue, BaseTypingClassWithGenerics, BaseTypingInstance
from jedi.inference.gradual.type_var import TypeVarClass
from jedi.inference.gradual.generics import LazyGenericManager, TupleGenericManager
_PROXY_CLASS_TYPES = 'Tuple Generic Protocol Callable Type'.split()
_TYPE_ALIAS_TYPES = {'List': 'builtins.list', 'Dict': 'builtins.dict', 'Set': 'builtins.set', 'FrozenSet': 'builtins.frozenset', 'ChainMap': 'collections.ChainMap', 'Counter': 'collections.Counter', 'DefaultDict': 'collections.defaultdict', 'Deque': 'collections.deque'}
_PROXY_TYPES = 'Optional Union ClassVar Annotated'.split()

class TypingModuleName(NameWrapper):
    pass

class TypingModuleFilterWrapper(FilterWrapper):
    name_wrapper_class = TypingModuleName

class ProxyWithGenerics(BaseTypingClassWithGenerics):
    pass

class ProxyTypingValue(BaseTypingValue):
    index_class = ProxyWithGenerics

class _TypingClassMixin(ClassMixin):
    pass

class TypingClassWithGenerics(ProxyWithGenerics, _TypingClassMixin):
    pass

class ProxyTypingClassValue(ProxyTypingValue, _TypingClassMixin):
    index_class = TypingClassWithGenerics

class TypeAlias(LazyValueWrapper):

    def __init__(self, parent_context, origin_tree_name, actual):
        self.inference_state = parent_context.inference_state
        self.parent_context = parent_context
        self._origin_tree_name = origin_tree_name
        self._actual = actual

    def __repr__(self):
        return f'<{self.__class__.__name__}: {self._actual}>'

class Callable(BaseTypingInstance):

    def py__call__(self, arguments):
        """
            def x() -> Callable[[Callable[..., _T]], _T]: ...
        """
        # Since we can't access _T directly, we'll return a generic result
        return ValueSet([self.inference_state.builtins_module.py__getattribute__('object')])

class Tuple(BaseTypingInstance):
    pass

class Generic(BaseTypingInstance):
    pass

class Protocol(BaseTypingInstance):
    pass

class AnyClass(BaseTypingValue):
    pass

class OverloadFunction(BaseTypingValue):
    pass

class NewTypeFunction(ValueWrapper):
    pass

class NewType(Value):

    def __init__(self, inference_state, parent_context, tree_node, type_value_set):
        super().__init__(inference_state, parent_context)
        self._type_value_set = type_value_set
        self.tree_node = tree_node

    def __repr__(self) -> str:
        return '<NewType: %s>%s' % (self.tree_node, self._type_value_set)

class CastFunction(ValueWrapper):
    pass

class TypedDictClass(BaseTypingValue):
    """
    This class has no responsibilities and is just here to make sure that typed
    dicts can be identified.
    """

class TypedDict(LazyValueWrapper):
    """Represents the instance version of ``TypedDictClass``."""

    def __init__(self, definition_class):
        self.inference_state = definition_class.inference_state
        self.parent_context = definition_class.parent_context
        self.tree_node = definition_class.tree_node
        self._definition_class = definition_class
