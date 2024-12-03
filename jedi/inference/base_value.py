"""
Values are the "values" that Python would return. However Values are at the
same time also the "values" that a user is currently sitting in.

A ValueSet is typically used to specify the return of a function or any other
static analysis operation. In jedi there are always multiple returns and not
just one.
"""
from functools import reduce
from operator import add
from itertools import zip_longest
from parso.python.tree import Name
from jedi import debug
from jedi.parser_utils import clean_scope_docstring
from jedi.inference.helpers import SimpleGetItemNotFound
from jedi.inference.utils import safe_property
from jedi.inference.cache import inference_state_as_method_param_cache
from jedi.cache import memoize_method
sentinel = object()

class HasNoContext(Exception):
    pass

class HelperValueMixin:

    def py__getattribute__(self, name_or_str, name_context=None, position=None, analysis_errors=True):
        """
        :param position: Position of the last statement -> tuple of line, column
        """
        if isinstance(name_or_str, str):
            name = name_or_str
        else:
            name = name_or_str.value

        if name_context is None:
            name_context = self.parent_context

        try:
            return self._get_attribute(name, name_context, position, analysis_errors)
        except AttributeError:
            if analysis_errors:
                self.inference_state.analysis.add(
                    'attribute-error',
                    name_context,
                    position,
                    message="Attribute '%s' not found" % name
                )
            return NO_VALUES

class Value(HelperValueMixin):
    """
    To be implemented by subclasses.
    """
    tree_node = None
    array_type = None
    api_type = 'not_defined_please_report_bug'

    def __init__(self, inference_state, parent_context=None):
        self.inference_state = inference_state
        self.parent_context = parent_context

    def py__bool__(self):
        """
        Since Wrapper is a super class for classes, functions and modules,
        the return value will always be true.
        """
        return True

    def py__getattribute__alternatives(self, name_or_str):
        """
        For now a way to add values in cases like __getattr__.
        """
        return NO_VALUES

    def infer_type_vars(self, value_set):
        """
        When the current instance represents a type annotation, this method
        tries to find information about undefined type vars and returns a dict
        from type var name to value set.

        This is for example important to understand what `iter([1])` returns.
        According to typeshed, `iter` returns an `Iterator[_T]`:

            def iter(iterable: Iterable[_T]) -> Iterator[_T]: ...

        This functions would generate `int` for `_T` in this case, because it
        unpacks the `Iterable`.

        Parameters
        ----------

        `self`: represents the annotation of the current parameter to infer the
            value for. In the above example, this would initially be the
            `Iterable[_T]` of the `iterable` parameter and then, when recursing,
            just the `_T` generic parameter.

        `value_set`: represents the actual argument passed to the parameter
            we're inferred for, or (for recursive calls) their types. In the
            above example this would first be the representation of the list
            `[1]` and then, when recursing, just of `1`.
        """
        return {}

def iterate_values(values, contextualized_node=None, is_async=False):
    """
    Calls `iterate`, on all values but ignores the ordering and just returns
    all values that the iterate functions yield.
    """
    return ValueSet.from_sets(
        value.iterate(contextualized_node, is_async)
        for value in values
        if value.is_instance()
    )

class _ValueWrapperBase(HelperValueMixin):

    def __getattr__(self, name):
        assert name != '_wrapped_value', 'Problem with _get_wrapped_value'
        return getattr(self._wrapped_value, name)

class LazyValueWrapper(_ValueWrapperBase):

    def __init__(self, inference_state):
        self.inference_state = inference_state

    def __repr__(self):
        return '<%s>' % self.__class__.__name__

class ValueWrapper(_ValueWrapperBase):

    def __init__(self, wrapped_value):
        self._wrapped_value = wrapped_value
        self.inference_state = wrapped_value.inference_state
        self.parent_context = wrapped_value.parent_context

    def __repr__(self):
        return '%s(%s)' % (self.__class__.__name__, self._wrapped_value)

class TreeValue(Value):

    def __init__(self, inference_state, parent_context, tree_node):
        super().__init__(inference_state, parent_context)
        self.tree_node = tree_node
        self._value_cache = {}

    def __repr__(self):
        return '<%s: %s>' % (self.__class__.__name__, self.tree_node)

    def get_value(self, name):
        if name not in self._value_cache:
            self._value_cache[name] = self._infer_value(name)
        return self._value_cache[name]

    def _infer_value(self, name):
        # This method should be implemented in subclasses
        raise NotImplementedError

class ContextualizedNode:

    def __init__(self, context, node):
        self.context = context
        self.node = node

    def __repr__(self):
        return '<%s: %s in %s>' % (self.__class__.__name__, self.node, self.context)

class ValueSet:

    def __init__(self, iterable):
        self._set = frozenset(iterable)
        for value in iterable:
            assert not isinstance(value, ValueSet)

    @classmethod
    def from_sets(cls, sets):
        """
        Used to work with an iterable of set.
        """
        return cls(set().union(*sets))

    def __or__(self, other):
        return self._from_frozen_set(self._set | other._set)

    def __and__(self, other):
        return self._from_frozen_set(self._set & other._set)

    def __iter__(self):
        return iter(self._set)

    def __bool__(self):
        return bool(self._set)

    def __len__(self):
        return len(self._set)

    def __repr__(self):
        return 'S{%s}' % ', '.join((str(s) for s in self._set))

    def __getattr__(self, name):

        def mapper(*args, **kwargs):
            return self.from_sets((getattr(value, name)(*args, **kwargs) for value in self._set))
        return mapper

    def __eq__(self, other):
        return self._set == other._set

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        return hash(self._set)
NO_VALUES = ValueSet([])
