from pathlib import Path
from typing import Optional
from jedi.inference.cache import inference_state_method_cache
from jedi.inference.filters import DictFilter
from jedi.inference.names import ValueNameMixin, AbstractNameDefinition
from jedi.inference.base_value import Value
from jedi.inference.value.module import SubModuleDictMixin
from jedi.inference.context import NamespaceContext

class ImplicitNSName(ValueNameMixin, AbstractNameDefinition):
    """
    Accessing names for implicit namespace packages should infer to nothing.
    This object will prevent Jedi from raising exceptions
    """

    def __init__(self, implicit_ns_value, string_name):
        self._value = implicit_ns_value
        self.string_name = string_name

class ImplicitNamespaceValue(Value, SubModuleDictMixin):
    """
    Provides support for implicit namespace packages
    """
    api_type = 'namespace'
    parent_context = None

    def __init__(self, inference_state, string_names, paths):
        super().__init__(inference_state, parent_context=None)
        self.inference_state = inference_state
        self.string_names = string_names
        self._paths = paths

    def py__package__(self):
        """Return the fullname of the package"""
        return '.'.join(self.string_names)

    def __repr__(self):
        return '<%s: %s>' % (self.__class__.__name__, self.py__name__())
