from jedi import debug
from jedi.inference.base_value import ValueSet, NO_VALUES, ValueWrapper
from jedi.inference.gradual.base import BaseTypingValue

class TypeVarClass(ValueWrapper):
    def __init__(self, inference_state, name, constraints=None, bound=None, covariant=False, contravariant=False):
        super().__init__(inference_state)
        self.name = name
        self.constraints = constraints or []
        self.bound = bound
        self.covariant = covariant
        self.contravariant = contravariant

    def __repr__(self):
        return f'<TypeVarClass {self.name}>'

class TypeVar(BaseTypingValue):

    def __init__(self, parent_context, tree_name, var_name, unpacked_args):
        super().__init__(parent_context, tree_name)
        self._var_name = var_name
        self._constraints_lazy_values = []
        self._bound_lazy_value = None
        self._covariant_lazy_value = None
        self._contravariant_lazy_value = None
        for key, lazy_value in unpacked_args:
            if key is None:
                self._constraints_lazy_values.append(lazy_value)
            elif key == 'bound':
                self._bound_lazy_value = lazy_value
            elif key == 'covariant':
                self._covariant_lazy_value = lazy_value
            elif key == 'contravariant':
                self._contravariant_lazy_value = lazy_value
            else:
                debug.warning('Invalid TypeVar param name %s', key)

    def __repr__(self):
        return '<%s: %s>' % (self.__class__.__name__, self.py__name__())

    def py__name__(self):
        return self._var_name

    def is_bound(self):
        return self._bound_lazy_value is not None

    def is_constrained(self):
        return bool(self._constraints_lazy_values)

    def get_constraints(self):
        return [lazy_value.infer() for lazy_value in self._constraints_lazy_values]

    def get_bound(self):
        if self._bound_lazy_value:
            return self._bound_lazy_value.infer()
        return NO_VALUES

    def is_covariant(self):
        return self._covariant_lazy_value and self._covariant_lazy_value.infer().py__bool__()

    def is_contravariant(self):
        return self._contravariant_lazy_value and self._contravariant_lazy_value.infer().py__bool__()

class TypeWrapper(ValueWrapper):

    def __init__(self, wrapped_value, original_value):
        super().__init__(wrapped_value)
        self._original_value = original_value

    def __repr__(self):
        return f'<TypeWrapper {self._wrapped_value}>'

    def get_original_value(self):
        return self._original_value

    def py__name__(self):
        return self._wrapped_value.py__name__()

    def is_same_class(self, class_value):
        return self._wrapped_value.is_same_class(class_value)

    def py__class__(self):
        return self._wrapped_value.py__class__()
