"""
A module to deal with stuff like `list.append` and `set.add`.

Array modifications
*******************

If the content of an array (``set``/``list``) is requested somewhere, the
current module will be checked for appearances of ``arr.append``,
``arr.insert``, etc.  If the ``arr`` name points to an actual array, the
content will be added

This can be really cpu intensive, as you can imagine. Because |jedi| has to
follow **every** ``append`` and check whether it's the right array. However this
works pretty good, because in *slow* cases, the recursion detector and other
settings will stop this process.

It is important to note that:

1. Array modifications work only in the current module.
2. Jedi only checks Array additions; ``list.pop``, etc are ignored.
"""
from jedi import debug
from jedi import settings
from jedi.inference import recursion
from jedi.inference.base_value import ValueSet, NO_VALUES, HelperValueMixin, ValueWrapper
from jedi.inference.lazy_value import LazyKnownValues
from jedi.inference.helpers import infer_call_of_leaf
from jedi.inference.cache import inference_state_method_cache
_sentinel = object()

def check_array_additions(context, sequence):
    """ Just a mapper function for the internal _internal_check_array_additions """
    return _internal_check_array_additions(context, sequence)

@inference_state_method_cache(default=NO_VALUES)
@debug.increase_indent
def _internal_check_array_additions(context, sequence):
    """
    Checks if a `Array` has "add" (append, insert, extend) statements:

    >>> a = [""]
    >>> a.append(1)
    """
    from jedi.inference.helpers import infer_call_of_leaf
    from jedi.inference.value import iterable

    def check_additions(value_node):
        additions = NO_VALUES
        for name, trailer in value_node.get_defined_names_and_trailers():
            if name.value in ('append', 'insert', 'extend'):
                trailer_nodes = trailer.children[1:-1]  # Skip parentheses
                if name.value == 'extend':
                    additions |= ValueSet.from_sets(
                        lazy_value.infer()
                        for lazy_value in iterate_argument_clinic(context.inference_state, trailer_nodes, 'extend(iterable)')
                    )
                else:
                    additions |= ValueSet.from_sets(
                        infer_call_of_leaf(context, trailer_nodes[0])
                        for _ in iterate_argument_clinic(context.inference_state, trailer_nodes, f'{name.value}(object)')
                    )
        return additions

    added_values = NO_VALUES
    for value in sequence.infer():
        if value.is_instance() and isinstance(value, iterable.Sequence):
            added_values |= check_additions(value.name.tree_name)

    return added_values

def get_dynamic_array_instance(instance, arguments):
    """Used for set() and list() instances."""
    from jedi.inference.value import iterable

    sequence = instance.get_annotated_class_object()
    if isinstance(sequence, iterable.Sequence):
        return _DynamicArrayAdditions(instance, arguments)
    return instance

class _DynamicArrayAdditions(HelperValueMixin):
    """
    Used for the usage of set() and list().
    This is definitely a hack, but a good one :-)
    It makes it possible to use set/list conversions.

    This is not a proper context, because it doesn't have to be. It's not used
    in the wild, it's just used within typeshed as an argument to `__init__`
    for set/list and never used in any other place.
    """

    def __init__(self, instance, arguments):
        self._instance = instance
        self._arguments = arguments
        self.inference_state = instance.inference_state
        self._context = instance.parent_context

class _Modification(ValueWrapper):

    def __init__(self, wrapped_value, assigned_values, contextualized_key):
        super().__init__(wrapped_value)
        self._assigned_values = assigned_values
        self._contextualized_key = contextualized_key

class DictModification(_Modification):
    pass

class ListModification(_Modification):
    pass
