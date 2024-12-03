""" A universal module with functions / classes without dependencies. """
import functools
import re
import os
import sys
_sep = os.path.sep
if os.path.altsep is not None:
    _sep += os.path.altsep
_path_re = re.compile('(?:\\.[^{0}]+|[{0}]__init__\\.py)$'.format(re.escape(_sep)))
del _sep

def unite(iterable):
    """Turns a two dimensional array into a one dimensional."""
    return [item for sublist in iterable for item in sublist]

class UncaughtAttributeError(Exception):
    """
    Important, because `__getattr__` and `hasattr` catch AttributeErrors
    implicitly. This is really evil (mainly because of `__getattr__`).
    Therefore this class originally had to be derived from `BaseException`
    instead of `Exception`.  But because I removed relevant `hasattr` from
    the code base, we can now switch back to `Exception`.

    :param base: return values of sys.exc_info().
    """

def reraise_uncaught(func):
    """
    Re-throw uncaught `AttributeError`.

    Usage:  Put ``@rethrow_uncaught`` in front of the function
    which does **not** suppose to raise `AttributeError`.

    AttributeError is easily get caught by `hasattr` and another
    ``except AttributeError`` clause.  This becomes problem when you use
    a lot of "dynamic" attributes (e.g., using ``@property``) because you
    can't distinguish if the property does not exist for real or some code
    inside of the "dynamic" attribute through that error.  In a well
    written code, such error should not exist but getting there is very
    difficult.  This decorator is to help us getting there by changing
    `AttributeError` to `UncaughtAttributeError` to avoid unexpected catch.
    This helps us noticing bugs earlier and facilitates debugging.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except AttributeError as e:
            raise UncaughtAttributeError(sys.exc_info()) from e
    return wrapper

class PushBackIterator:

    def __init__(self, iterator):
        self.pushes = []
        self.iterator = iterator
        self.current = None

    def __iter__(self):
        return self

    def __next__(self):
        if self.pushes:
            self.current = self.pushes.pop()
        else:
            self.current = next(self.iterator)
        return self.current
