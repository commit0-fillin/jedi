"""
Implementations of standard library functions, because it's not possible to
understand them with Jedi.

To add a new implementation, create a function and add it to the
``_implemented`` dict at the bottom of this module.

Note that this module exists only to implement very specific functionality in
the standard library. The usual way to understand the standard library is the
compiled module that returns the types for C-builtins.
"""
import parso
import os
from inspect import Parameter
from jedi import debug
from jedi.inference.utils import safe_property
from jedi.inference.helpers import get_str_or_none
from jedi.inference.arguments import iterate_argument_clinic, ParamIssue, repack_with_argument_clinic, AbstractArguments, TreeArgumentsWrapper
from jedi.inference import analysis
from jedi.inference import compiled
from jedi.inference.value.instance import AnonymousMethodExecutionContext, MethodExecutionContext
from jedi.inference.base_value import ContextualizedNode, NO_VALUES, ValueSet, ValueWrapper, LazyValueWrapper
from jedi.inference.value import ClassValue, ModuleValue
from jedi.inference.value.klass import ClassMixin
from jedi.inference.value.function import FunctionMixin
from jedi.inference.value import iterable
from jedi.inference.lazy_value import LazyTreeValue, LazyKnownValue, LazyKnownValues
from jedi.inference.names import ValueName, BaseTreeParamName
from jedi.inference.filters import AttributeOverwrite, publish_method, ParserTreeFilter, DictFilter
from jedi.inference.signature import AbstractSignature, SignatureWrapper
_NAMEDTUPLE_CLASS_TEMPLATE = "_property = property\n_tuple = tuple\nfrom operator import itemgetter as _itemgetter\nfrom collections import OrderedDict\n\nclass {typename}(tuple):\n    __slots__ = ()\n\n    _fields = {field_names!r}\n\n    def __new__(_cls, {arg_list}):\n        'Create new instance of {typename}({arg_list})'\n        return _tuple.__new__(_cls, ({arg_list}))\n\n    @classmethod\n    def _make(cls, iterable, new=tuple.__new__, len=len):\n        'Make a new {typename} object from a sequence or iterable'\n        result = new(cls, iterable)\n        if len(result) != {num_fields:d}:\n            raise TypeError('Expected {num_fields:d} arguments, got %d' % len(result))\n        return result\n\n    def _replace(_self, **kwds):\n        'Return a new {typename} object replacing specified fields with new values'\n        result = _self._make(map(kwds.pop, {field_names!r}, _self))\n        if kwds:\n            raise ValueError('Got unexpected field names: %r' % list(kwds))\n        return result\n\n    def __repr__(self):\n        'Return a nicely formatted representation string'\n        return self.__class__.__name__ + '({repr_fmt})' % self\n\n    def _asdict(self):\n        'Return a new OrderedDict which maps field names to their values.'\n        return OrderedDict(zip(self._fields, self))\n\n    def __getnewargs__(self):\n        'Return self as a plain tuple.  Used by copy and pickle.'\n        return tuple(self)\n\n    # These methods were added by Jedi.\n    # __new__ doesn't really work with Jedi. So adding this to nametuples seems\n    # like the easiest way.\n    def __init__(self, {arg_list}):\n        'A helper function for namedtuple.'\n        self.__iterable = ({arg_list})\n\n    def __iter__(self):\n        for i in self.__iterable:\n            yield i\n\n    def __getitem__(self, y):\n        return self.__iterable[y]\n\n{field_defs}\n"
_NAMEDTUPLE_FIELD_TEMPLATE = "    {name} = _property(_itemgetter({index:d}), doc='Alias for field number {index:d}')\n"

def argument_clinic(clinic_string, want_value=False, want_context=False, want_arguments=False, want_inference_state=False, want_callback=False):
    """
    Works like Argument Clinic (PEP 436), to validate function params.
    """
    def decorator(func):
        def wrapper(value, *args, **kwargs):
            inference_state = value.inference_state
            arguments = None
            context = None
            if want_arguments:
                arguments = kwargs.get('arguments', None)
            if want_context:
                context = kwargs.get('context', None)
            
            try:
                clinic_args = iterate_argument_clinic(
                    inference_state, arguments.unpack() if arguments else [], clinic_string
                )
                if want_value:
                    clinic_args = list(clinic_args)
                    clinic_args.insert(0, ('self', LazyKnownValue(value)))
                if want_inference_state:
                    kwargs['inference_state'] = inference_state
                if want_context:
                    kwargs['context'] = context
                if want_arguments:
                    kwargs['arguments'] = arguments
                if want_callback:
                    kwargs['callback'] = lambda value_set: ValueSet.from_sets(
                        func(value, *[v.infer() for k, v in clinic_args], **kwargs)
                    )
                return func(value, *[v.infer() for k, v in clinic_args], **kwargs)
            except ParamIssue as issue:
                debug.warning('ParamIssue: %s', issue)
                return NO_VALUES

        return wrapper
    return decorator

class SuperInstance(LazyValueWrapper):
    """To be used like the object ``super`` returns."""

    def __init__(self, inference_state, instance):
        super().__init__(inference_state)
        self._instance = instance
        self._class = instance.class_value
        self._super_class = None
        for base in self._class.py__bases__():
            if base != instance.class_value:
                self._super_class = base
                break

class ReversedObject(AttributeOverwrite):

    def __init__(self, reversed_obj, iter_list):
        super().__init__(reversed_obj)
        self._iter_list = iter_list
        self._iter_list.reverse()

class StaticMethodObject(ValueWrapper):
    pass

class ClassMethodObject(ValueWrapper):

    def __init__(self, class_method_obj, function):
        super().__init__(class_method_obj)
        self._function = function

class ClassMethodGet(ValueWrapper):

    def __init__(self, get_method, klass, function):
        super().__init__(get_method)
        self._class = klass
        self._function = function

class ClassMethodArguments(TreeArgumentsWrapper):

    def __init__(self, klass, arguments):
        super().__init__(arguments)
        self._class = klass

class PropertyObject(AttributeOverwrite, ValueWrapper):
    api_type = 'property'

    def __init__(self, property_obj, function):
        super().__init__(property_obj)
        self._function = function

def collections_namedtuple(value, arguments, callback):
    """
    Implementation of the namedtuple function.

    This has to be done by processing the namedtuple class template and
    inferring the result.
    """
    from jedi.inference.value import FakeTypedDict

    def execute(params):
        try:
            typename, field_names = params
            if not isinstance(typename, str):
                return NO_VALUES
            if isinstance(field_names, str):
                field_names = field_names.replace(',', ' ').split()
            elif isinstance(field_names, (list, tuple)):
                field_names = [str(v) for v in field_names]
            else:
                return NO_VALUES
            
            class_template = _NAMEDTUPLE_CLASS_TEMPLATE.format(
                typename=typename,
                field_names=repr(tuple(field_names)),
                num_fields=len(field_names),
                arg_list=repr(tuple(field_names)).replace("'", "")[1:-1],
                repr_fmt='(' + ', '.join(f'{name}=%r' for name in field_names) + ')',
                field_defs='\n'.join(_NAMEDTUPLE_FIELD_TEMPLATE.format(index=index, name=name)
                                     for index, name in enumerate(field_names))
            )
            module = value.inference_state.grammar.parse(class_template)
            generated_class = next(module.iter_classdefs())
            return ValueSet([value.inference_state.compiled_subprocess.get_or_create_instance(generated_class)])
        except Exception:
            return NO_VALUES

    return execute(arguments.unpack())

class PartialObject(ValueWrapper):

    def __init__(self, actual_value, arguments, instance=None):
        super().__init__(actual_value)
        self._arguments = arguments
        self._instance = instance
        self.inference_state = actual_value.inference_state

    def py__doc__(self):
        """
        In CPython partial does not replace the docstring. However we are still
        imitating it here, because we want this docstring to be worth something
        for the user.
        """
        return self._actual_value.py__doc__()

class PartialMethodObject(PartialObject):
    pass

class PartialSignature(SignatureWrapper):

    def __init__(self, wrapped_signature, skipped_arg_count, skipped_arg_set):
        super().__init__(wrapped_signature)
        self._skipped_arg_count = skipped_arg_count
        self._skipped_arg_set = skipped_arg_set

class MergedPartialArguments(AbstractArguments):

    def __init__(self, partial_arguments, call_arguments, instance=None):
        self._partial_arguments = partial_arguments
        self._call_arguments = call_arguments
        self._instance = instance

class DataclassWrapper(ValueWrapper, ClassMixin):
    pass

class DataclassSignature(AbstractSignature):

    def __init__(self, value, param_names):
        super().__init__(value)
        self._param_names = param_names

class DataclassParamName(BaseTreeParamName):

    def __init__(self, parent_context, tree_name, annotation_node, default_node):
        super().__init__(parent_context, tree_name)
        self.annotation_node = annotation_node
        self.default_node = default_node

class ItemGetterCallable(ValueWrapper):

    def __init__(self, instance, args_value_set):
        super().__init__(instance)
        self._args_value_set = args_value_set

class WrapsCallable(ValueWrapper):
    pass

class Wrapped(ValueWrapper, FunctionMixin):

    def __init__(self, func, original_function):
        super().__init__(func)
        self._original_function = original_function
_implemented = {'builtins': {'getattr': builtins_getattr, 'type': builtins_type, 'super': builtins_super, 'reversed': builtins_reversed, 'isinstance': builtins_isinstance, 'next': builtins_next, 'iter': builtins_iter, 'staticmethod': builtins_staticmethod, 'classmethod': builtins_classmethod, 'property': builtins_property}, 'copy': {'copy': _return_first_param, 'deepcopy': _return_first_param}, 'json': {'load': lambda value, arguments, callback: NO_VALUES, 'loads': lambda value, arguments, callback: NO_VALUES}, 'collections': {'namedtuple': collections_namedtuple}, 'functools': {'partial': functools_partial, 'partialmethod': functools_partialmethod, 'wraps': _functools_wraps}, '_weakref': {'proxy': _return_first_param}, 'random': {'choice': _random_choice}, 'operator': {'itemgetter': _operator_itemgetter}, 'abc': {'abstractmethod': _return_first_param}, 'typing': {'_alias': lambda value, arguments, callback: NO_VALUES, 'runtime_checkable': lambda value, arguments, callback: NO_VALUES}, 'dataclasses': {'dataclass': _dataclass}, 'attr': {'define': _dataclass, 'frozen': _dataclass}, 'attrs': {'define': _dataclass, 'frozen': _dataclass}, 'os.path': {'dirname': _create_string_input_function(os.path.dirname), 'abspath': _create_string_input_function(os.path.abspath), 'relpath': _create_string_input_function(os.path.relpath), 'join': _os_path_join}}

class EnumInstance(LazyValueWrapper):

    def __init__(self, cls, name):
        self.inference_state = cls.inference_state
        self._cls = cls
        self._name = name
        self.tree_node = self._name.tree_name
