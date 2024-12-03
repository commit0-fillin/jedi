"""
Imitate the parser representation.
"""
import re
from functools import partial
from inspect import Parameter
from pathlib import Path
from typing import Optional
from jedi import debug
from jedi.inference.utils import to_list
from jedi.cache import memoize_method
from jedi.inference.filters import AbstractFilter
from jedi.inference.names import AbstractNameDefinition, ValueNameMixin, ParamNameInterface
from jedi.inference.base_value import Value, ValueSet, NO_VALUES
from jedi.inference.lazy_value import LazyKnownValue
from jedi.inference.compiled.access import _sentinel
from jedi.inference.cache import inference_state_function_cache
from jedi.inference.helpers import reraise_getitem_errors
from jedi.inference.signature import BuiltinSignature
from jedi.inference.context import CompiledContext, CompiledModuleContext

class CheckAttribute:
    """Raises :exc:`AttributeError` if the attribute X is not available."""

    def __init__(self, check_name=None):
        self.check_name = check_name

    def __call__(self, func):
        self.func = func
        if self.check_name is None:
            self.check_name = func.__name__[2:]
        return self

    def __get__(self, instance, owner):
        if instance is None:
            return self
        instance.access_handle.getattr_paths(self.check_name)
        return partial(self.func, instance)

class CompiledValue(Value):

    def __init__(self, inference_state, access_handle, parent_context=None):
        super().__init__(inference_state, parent_context)
        self.access_handle = access_handle

    def __repr__(self):
        return '<%s: %s>' % (self.__class__.__name__, self.access_handle.get_repr())

class CompiledModule(CompiledValue):
    file_io = None

class CompiledName(AbstractNameDefinition):

    def __init__(self, inference_state, parent_value, name, is_descriptor):
        self._inference_state = inference_state
        self.parent_context = parent_value.as_context()
        self._parent_value = parent_value
        self.string_name = name
        self.is_descriptor = is_descriptor

    def __repr__(self):
        try:
            name = self.parent_context.name
        except AttributeError:
            name = None
        return '<%s: (%s).%s>' % (self.__class__.__name__, name, self.string_name)

class SignatureParamName(ParamNameInterface, AbstractNameDefinition):

    def __init__(self, compiled_value, signature_param):
        self.parent_context = compiled_value.parent_context
        self._signature_param = signature_param

class UnresolvableParamName(ParamNameInterface, AbstractNameDefinition):

    def __init__(self, compiled_value, name, default):
        self.parent_context = compiled_value.parent_context
        self.string_name = name
        self._default = default

class CompiledValueName(ValueNameMixin, AbstractNameDefinition):

    def __init__(self, value, name):
        self.string_name = name
        self._value = value
        self.parent_context = value.parent_context

class EmptyCompiledName(AbstractNameDefinition):
    """
    Accessing some names will raise an exception. To avoid not having any
    completions, just give Jedi the option to return this object. It infers to
    nothing.
    """

    def __init__(self, inference_state, name):
        self.parent_context = inference_state.builtins_module
        self.string_name = name

class CompiledValueFilter(AbstractFilter):

    def __init__(self, inference_state, compiled_value, is_instance=False):
        self._inference_state = inference_state
        self.compiled_value = compiled_value
        self.is_instance = is_instance

    def _get(self, name, allowed_getattr_callback, in_dir_callback, check_has_attribute=False):
        """
        To remove quite a few access calls we introduced the callback here.
        """
        access_handle = self.compiled_value.access_handle
        
        if check_has_attribute:
            try:
                access_handle.getattr_paths(name)
            except AttributeError:
                return []

        if name in access_handle.dir():
            if in_dir_callback() is False:
                return []
        else:
            if not access_handle.has_iter():
                if allowed_getattr_callback() is False:
                    return []

        try:
            return [CompiledName(
                self._inference_state,
                self.compiled_value,
                name,
                access_handle.is_descriptor(name)
            )]
        except AttributeError:
            return []

    def __repr__(self):
        return '<%s: %s>' % (self.__class__.__name__, self.compiled_value)
docstr_defaults = {'floating point number': 'float', 'character': 'str', 'integer': 'int', 'dictionary': 'dict', 'string': 'str'}

def _parse_function_doc(doc):
    """
    Takes a function and returns the params and return value as a tuple.
    This is nothing more than a docstring parser.

    TODO docstrings like utime(path, (atime, mtime)) and a(b [, b]) -> None
    TODO docstrings like 'tuple of integers'
    """
    if doc is None:
        return [], None

    doc = doc.strip()
    
    # Try to parse the first line for parameters and return type
    first_line = doc.split('\n')[0]
    param_str, _, return_str = first_line.partition('->')
    
    # Parse parameters
    params = []
    if '(' in param_str and ')' in param_str:
        param_str = param_str[param_str.index('(') + 1:param_str.rindex(')')]
        for param in param_str.split(','):
            param = param.strip()
            if param:
                param_name = param.split(':')[0].strip()
                params.append(param_name)
    
    # Parse return type
    return_type = None
    if return_str:
        return_str = return_str.strip()
        for key, value in docstr_defaults.items():
            if key in return_str.lower():
                return_type = value
                break
        if return_type is None and return_str != 'None':
            return_type = return_str
    
    return params, return_type

def _normalize_create_args(func):
    """The cache doesn't care about keyword vs. normal args."""
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)
    return wrapper
