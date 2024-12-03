import inspect
import types
import traceback
import sys
import operator as op
from collections import namedtuple
import warnings
import re
import builtins
import typing
from pathlib import Path
from typing import Optional, Tuple
from jedi.inference.compiled.getattr_static import getattr_static
ALLOWED_GETITEM_TYPES = (str, list, tuple, bytes, bytearray, dict)
MethodDescriptorType = type(str.replace)
NOT_CLASS_TYPES = (types.BuiltinFunctionType, types.CodeType, types.FrameType, types.FunctionType, types.GeneratorType, types.GetSetDescriptorType, types.LambdaType, types.MemberDescriptorType, types.MethodType, types.ModuleType, types.TracebackType, MethodDescriptorType, types.MappingProxyType, types.SimpleNamespace, types.DynamicClassAttribute)
MethodDescriptorType = type(str.replace)
WrapperDescriptorType = type(set.__iter__)
object_class_dict = type.__dict__['__dict__'].__get__(object)
ClassMethodDescriptorType = type(object_class_dict['__subclasshook__'])
_sentinel = object()
COMPARISON_OPERATORS = {'==': op.eq, '!=': op.ne, 'is': op.is_, 'is not': op.is_not, '<': op.lt, '<=': op.le, '>': op.gt, '>=': op.ge}
_OPERATORS = {'+': op.add, '-': op.sub}
_OPERATORS.update(COMPARISON_OPERATORS)
ALLOWED_DESCRIPTOR_ACCESS = (types.FunctionType, types.GetSetDescriptorType, types.MemberDescriptorType, MethodDescriptorType, WrapperDescriptorType, ClassMethodDescriptorType, staticmethod, classmethod)
SignatureParam = namedtuple('SignatureParam', 'name has_default default default_string has_annotation annotation annotation_string kind_name')

class AccessPath:

    def __init__(self, accesses):
        self.accesses = accesses

class DirectObjectAccess:

    def __init__(self, inference_state, obj):
        self._inference_state = inference_state
        self._obj = obj

    def __repr__(self):
        return '%s(%s)' % (self.__class__.__name__, self.get_repr())

    def get_annotation_name_and_args(self):
        """
        Returns Tuple[Optional[str], Tuple[AccessPath, ...]]
        """
        annotation = getattr(self._obj, '__annotations__', {}).get('return', None)
        if annotation is None:
            return None, ()
        
        name = getattr(annotation, '__name__', str(annotation))
        args = []
        
        if hasattr(annotation, '__args__'):
            for arg in annotation.__args__:
                if isinstance(arg, type):
                    args.append(AccessPath([arg.__name__]))
                else:
                    args.append(AccessPath([str(arg)]))
        
        return name, tuple(args)

    def get_dir_infos(self):
        """
        Used to return a couple of infos that are needed when accessing the sub
        objects of an objects
        """
        return [
            (name, getattr_static(self._obj, name))
            for name in dir(self._obj)
        ]

def _is_class_instance(obj):
    """Like inspect.* methods."""
    return (not isinstance(obj, type)
            and not isinstance(type(obj), types.ModuleType)
            and not isinstance(type(obj), NOT_CLASS_TYPES))
