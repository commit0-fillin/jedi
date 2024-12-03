"""
This module is about generics, like the `int` in `List[int]`. It's not about
the Generic class.
"""
from jedi import debug
from jedi.cache import memoize_method
from jedi.inference.utils import to_tuple
from jedi.inference.base_value import ValueSet, NO_VALUES
from jedi.inference.value.iterable import SequenceLiteralValue
from jedi.inference.helpers import is_string

class _AbstractGenericManager:
    pass

class LazyGenericManager(_AbstractGenericManager):

    def __init__(self, context_of_index, index_value):
        self._context_of_index = context_of_index
        self._index_value = index_value

    @memoize_method
    def _tuple(self):
        return tuple(self._context_of_index.infer_node(self._index_value))

    @memoize_method
    def __getitem__(self, index):
        return self._tuple()[index]()

    def __len__(self):
        return len(self._tuple())

    def __repr__(self):
        return '<LazyG>[%s]' % ', '.join((repr(x) for x in self.to_tuple()))

    def to_tuple(self):
        return self._tuple()

class TupleGenericManager(_AbstractGenericManager):

    def __init__(self, tup):
        self._tuple = tup

    def __getitem__(self, index):
        return self._tuple[index]

    def __len__(self):
        return len(self._tuple)

    def __repr__(self):
        return '<TupG>[%s]' % ', '.join((repr(x) for x in self.to_tuple()))

    def to_tuple(self):
        return self._tuple
