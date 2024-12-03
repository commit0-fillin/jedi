"""
Used only for REPL Completion.
"""
import inspect
from pathlib import Path
from jedi.parser_utils import get_cached_code_lines
from jedi import settings
from jedi.cache import memoize_method
from jedi.inference import compiled
from jedi.file_io import FileIO
from jedi.inference.names import NameWrapper
from jedi.inference.base_value import ValueSet, ValueWrapper, NO_VALUES
from jedi.inference.value import ModuleValue
from jedi.inference.cache import inference_state_function_cache, inference_state_method_cache
from jedi.inference.compiled.access import ALLOWED_GETITEM_TYPES, get_api_type
from jedi.inference.gradual.conversion import to_stub
from jedi.inference.context import CompiledContext, CompiledModuleContext, TreeContextMixin
_sentinel = object()

class MixedObject(ValueWrapper):
    """
    A ``MixedObject`` is used in two ways:

    1. It uses the default logic of ``parser.python.tree`` objects,
    2. except for getattr calls and signatures. The names dicts are generated
       in a fashion like ``CompiledValue``.

    This combined logic makes it possible to provide more powerful REPL
    completion. It allows side effects that are not noticable with the default
    parser structure to still be completable.

    The biggest difference from CompiledValue to MixedObject is that we are
    generally dealing with Python code and not with C code. This will generate
    fewer special cases, because we in Python you don't have the same freedoms
    to modify the runtime.
    """

    def __init__(self, compiled_value, tree_value):
        super().__init__(tree_value)
        self.compiled_value = compiled_value
        self.access_handle = compiled_value.access_handle

    def __repr__(self):
        return '<%s: %s; %s>' % (type(self).__name__, self.access_handle.get_repr(), self._wrapped_value)

class MixedContext(CompiledContext, TreeContextMixin):
    pass

class MixedModuleContext(CompiledModuleContext, MixedContext):
    pass

class MixedName(NameWrapper):
    """
    The ``CompiledName._compiled_value`` is our MixedObject.
    """

    def __init__(self, wrapped_name, parent_tree_value):
        super().__init__(wrapped_name)
        self._parent_tree_value = parent_tree_value

class MixedObjectFilter(compiled.CompiledValueFilter):

    def __init__(self, inference_state, compiled_value, tree_value):
        super().__init__(inference_state, compiled_value)
        self._tree_value = tree_value

def _get_object_to_check(python_object):
    """Check if inspect.getfile has a chance to find the source."""
    if inspect.ismodule(python_object):
        return python_object
    if inspect.isclass(python_object):
        return python_object
    if inspect.ismethod(python_object):
        return python_object.__func__
    if inspect.isfunction(python_object):
        return python_object
    if inspect.istraceback(python_object):
        return python_object.tb_frame
    if inspect.isframe(python_object):
        return python_object
    if inspect.iscode(python_object):
        return python_object
    return None
