from jedi.inference.cache import inference_state_method_cache
from jedi.inference.base_value import ValueSet, NO_VALUES, Value, iterator_to_value_set, LazyValueWrapper, ValueWrapper
from jedi.inference.compiled import builtin_from_name
from jedi.inference.value.klass import ClassFilter
from jedi.inference.value.klass import ClassMixin
from jedi.inference.utils import to_list
from jedi.inference.names import AbstractNameDefinition, ValueName
from jedi.inference.context import ClassContext
from jedi.inference.gradual.generics import TupleGenericManager

class _BoundTypeVarName(AbstractNameDefinition):
    """
    This type var was bound to a certain type, e.g. int.
    """

    def __init__(self, type_var, value_set):
        self._type_var = type_var
        self.parent_context = type_var.parent_context
        self._value_set = value_set

    def __repr__(self):
        return '<%s %s -> %s>' % (self.__class__.__name__, self.py__name__(), self._value_set)

    def py__name__(self):
        return self._type_var.py__name__()

class _TypeVarFilter:
    """
    A filter for all given variables in a class.

        A = TypeVar('A')
        B = TypeVar('B')
        class Foo(Mapping[A, B]):
            ...

    In this example we would have two type vars given: A and B
    """

    def __init__(self, generics, type_vars):
        self._generics = generics
        self._type_vars = type_vars
        self._tuple_mapping = dict(zip(self._type_vars, self._generics))

class _AnnotatedClassContext(ClassContext):
    pass

class DefineGenericBaseClass(LazyValueWrapper):

    def __init__(self, generics_manager):
        super().__init__(None)  # LazyValueWrapper requires an argument
        self._generics_manager = generics_manager

    def __repr__(self):
        return '<%s: %s%s>' % (self.__class__.__name__, self._wrapped_value, list(self.get_generics()))

    def get_generics(self):
        return self._generics_manager.to_tuple()

class GenericClass(DefineGenericBaseClass, ClassMixin):
    """
    A class that is defined with generics, might be something simple like:

        class Foo(Generic[T]): ...
        my_foo_int_cls = Foo[int]
    """

    def __init__(self, class_value, generics_manager):
        super().__init__(generics_manager)
        self._class_value = class_value
        self.inference_state = class_value.inference_state
        self.parent_context = class_value.parent_context

class _LazyGenericBaseClass:

    def __init__(self, class_value, lazy_base_class, generics_manager):
        self._class_value = class_value
        self._lazy_base_class = lazy_base_class
        self._generics_manager = generics_manager

    def __repr__(self):
        return '<%s: %s>' % (self.__class__.__name__, self._lazy_base_class)

class _GenericInstanceWrapper(ValueWrapper):
    pass

class _PseudoTreeNameClass(Value):
    """
    In typeshed, some classes are defined like this:

        Tuple: _SpecialForm = ...

    Now this is not a real class, therefore we have to do some workarounds like
    this class. Essentially this class makes it possible to goto that `Tuple`
    name, without affecting anything else negatively.
    """
    api_type = 'class'

    def __init__(self, parent_context, tree_name):
        super().__init__(parent_context.inference_state, parent_context)
        self._tree_name = tree_name

    def __repr__(self):
        return '%s(%s)' % (self.__class__.__name__, self._tree_name.value)

    def get_qualified_names(self):
        return (self._tree_name.value,)

class BaseTypingValue(LazyValueWrapper):

    def __init__(self, parent_context, tree_name):
        self.inference_state = parent_context.inference_state
        self.parent_context = parent_context
        self._tree_name = tree_name

    def __repr__(self):
        return '%s(%s)' % (self.__class__.__name__, self._tree_name.value)

class BaseTypingClassWithGenerics(DefineGenericBaseClass):

    def __init__(self, parent_context, tree_name, generics_manager):
        super().__init__(generics_manager)
        self.inference_state = parent_context.inference_state
        self.parent_context = parent_context
        self._tree_name = tree_name

    def __repr__(self):
        return '%s(%s%s)' % (self.__class__.__name__, self._tree_name.value, self._generics_manager)

class BaseTypingInstance(LazyValueWrapper):

    def __init__(self, parent_context, class_value, tree_name, generics_manager):
        self.inference_state = class_value.inference_state
        self.parent_context = parent_context
        self._class_value = class_value
        self._tree_name = tree_name
        self._generics_manager = generics_manager

    def __repr__(self):
        return '<%s: %s>' % (self.__class__.__name__, self._generics_manager)
