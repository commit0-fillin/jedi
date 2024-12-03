from abc import abstractproperty
from parso.tree import search_ancestor
from jedi import debug
from jedi import settings
from jedi.inference import compiled
from jedi.inference.compiled.value import CompiledValueFilter
from jedi.inference.helpers import values_from_qualified_names, is_big_annoying_library
from jedi.inference.filters import AbstractFilter, AnonymousFunctionExecutionFilter
from jedi.inference.names import ValueName, TreeNameDefinition, ParamName, NameWrapper
from jedi.inference.base_value import Value, NO_VALUES, ValueSet, iterator_to_value_set, ValueWrapper
from jedi.inference.lazy_value import LazyKnownValue, LazyKnownValues
from jedi.inference.cache import inference_state_method_cache
from jedi.inference.arguments import ValuesArguments, TreeArgumentsWrapper
from jedi.inference.value.function import FunctionValue, FunctionMixin, OverloadedFunctionValue, BaseFunctionExecutionContext, FunctionExecutionContext, FunctionNameInClass
from jedi.inference.value.klass import ClassFilter
from jedi.inference.value.dynamic_arrays import get_dynamic_array_instance
from jedi.parser_utils import function_is_staticmethod, function_is_classmethod

class InstanceExecutedParamName(ParamName):

    def __init__(self, instance, function_value, tree_name):
        super().__init__(function_value, tree_name, arguments=None)
        self._instance = instance

class AnonymousMethodExecutionFilter(AnonymousFunctionExecutionFilter):

    def __init__(self, instance, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._instance = instance

class AnonymousMethodExecutionContext(BaseFunctionExecutionContext):

    def __init__(self, instance, value):
        super().__init__(value)
        self.instance = instance

class MethodExecutionContext(FunctionExecutionContext):

    def __init__(self, instance, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance = instance

class AbstractInstanceValue(Value):
    api_type = 'instance'

    def __init__(self, inference_state, parent_context, class_value):
        super().__init__(inference_state, parent_context)
        self.class_value = class_value

    def __repr__(self):
        return '<%s of %s(%s)>' % (self.__class__.__name__, self.class_value, self._arguments)

class CompiledInstance(AbstractInstanceValue):

    def __init__(self, inference_state, parent_context, class_value, arguments):
        super().__init__(inference_state, parent_context, class_value)
        self._arguments = arguments

class _BaseTreeInstance(AbstractInstanceValue):

    def py__getattribute__alternatives(self, string_name):
        """
        Since nothing was inferred, now check the __getattr__ and
        __getattribute__ methods. Stubs don't need to be checked, because
        they don't contain any logic.
        """
        class_value = self.class_value
        for name in ('__getattr__', '__getattribute__'):
            try:
                method = class_value.py__getattribute__(name)
            except AttributeError:
                continue
            else:
                return method.execute_with_values(string_name)
        return NO_VALUES

    def py__get__(self, instance, class_value):
        """
        obj may be None.
        """
        try:
            descriptor = self.class_value.py__getattribute__('__get__')
        except AttributeError:
            return ValueSet([self])
        else:
            if instance is None:
                instance = NO_VALUES
            return descriptor.execute(instance, class_value)

class TreeInstance(_BaseTreeInstance):

    def __init__(self, inference_state, parent_context, class_value, arguments):
        if class_value.py__name__() in ['list', 'set'] and parent_context.get_root_context().is_builtins_module():
            if settings.dynamic_array_additions:
                arguments = get_dynamic_array_instance(self, arguments)
        super().__init__(inference_state, parent_context, class_value)
        self._arguments = arguments
        self.tree_node = class_value.tree_node

    def __repr__(self):
        return '<%s of %s(%s)>' % (self.__class__.__name__, self.class_value, self._arguments)

class AnonymousInstance(_BaseTreeInstance):
    _arguments = None

class CompiledInstanceName(NameWrapper):
    pass

class CompiledInstanceClassFilter(AbstractFilter):

    def __init__(self, instance, f):
        self._instance = instance
        self._class_filter = f

class BoundMethod(FunctionMixin, ValueWrapper):

    def __init__(self, instance, class_context, function):
        super().__init__(function)
        self.instance = instance
        self._class_context = class_context

    def __repr__(self):
        return '<%s: %s bound to %s>' % (self.__class__.__name__, self._wrapped_value, self.instance)

class CompiledBoundMethod(ValueWrapper):
    pass

class SelfName(TreeNameDefinition):
    """
    This name calculates the parent_context lazily.
    """

    def __init__(self, instance, class_context, tree_name):
        self._instance = instance
        self.class_context = class_context
        self.tree_name = tree_name

class LazyInstanceClassName(NameWrapper):

    def __init__(self, instance, class_member_name):
        super().__init__(class_member_name)
        self._instance = instance

class InstanceClassFilter(AbstractFilter):
    """
    This filter is special in that it uses the class filter and wraps the
    resulting names in LazyInstanceClassName. The idea is that the class name
    filtering can be very flexible and always be reflected in instances.
    """

    def __init__(self, instance, class_filter):
        self._instance = instance
        self._class_filter = class_filter

    def __repr__(self):
        return '<%s for %s>' % (self.__class__.__name__, self._class_filter)

class SelfAttributeFilter(ClassFilter):
    """
    This class basically filters all the use cases where `self.*` was assigned.
    """

    def __init__(self, instance, instance_class, node_context, origin_scope):
        super().__init__(class_value=instance_class, node_context=node_context, origin_scope=origin_scope, is_instance=True)
        self._instance = instance

class InstanceArguments(TreeArgumentsWrapper):

    def __init__(self, instance, arguments):
        super().__init__(arguments)
        self.instance = instance
