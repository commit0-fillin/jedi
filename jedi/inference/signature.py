from inspect import Parameter
from jedi.cache import memoize_method
from jedi import debug
from jedi import parser_utils

class _SignatureMixin:
    def get_param_names(self):
        return [param.name for param in self.value.get_param_names()]

    def get_return_annotation(self):
        return self.value.get_return_annotation()

    def get_signature_string(self):
        return self.value.get_signature_string()

class AbstractSignature(_SignatureMixin):

    def __init__(self, value, is_bound=False):
        self.value = value
        self.is_bound = is_bound
        self._function_value = None

    def __repr__(self):
        if self.value is self._function_value:
            return '<%s: %s>' % (self.__class__.__name__, self.value)
        return '<%s: %s, %s>' % (self.__class__.__name__, self.value, self._function_value)

    @property
    def function_value(self):
        return self._function_value

    @function_value.setter
    def function_value(self, value):
        self._function_value = value

class TreeSignature(AbstractSignature):

    def __init__(self, value, function_value=None, is_bound=False):
        super().__init__(value, is_bound)
        self.function_value = function_value or value

    def get_param_names(self):
        return self.value.get_param_names()

    def get_return_annotation(self):
        return self.value.get_return_annotation()

    def get_signature_string(self):
        return self.value.get_signature_string()

class BuiltinSignature(AbstractSignature):

    def __init__(self, value, return_string, function_value=None, is_bound=False):
        super().__init__(value, is_bound)
        self._return_string = return_string
        self.function_value = function_value

    def get_return_annotation(self):
        return self._return_string

    def get_param_names(self):
        return self.value.get_param_names()

    def get_signature_string(self):
        return self.value.get_signature_string()

class SignatureWrapper(_SignatureMixin):

    def __init__(self, wrapped_signature):
        self._wrapped_signature = wrapped_signature

    def __getattr__(self, name):
        return getattr(self._wrapped_signature, name)

    def get_param_names(self):
        return self._wrapped_signature.get_param_names()

    def get_return_annotation(self):
        return self._wrapped_signature.get_return_annotation()

    def get_signature_string(self):
        return self._wrapped_signature.get_signature_string()
