"""
A static version of getattr.
This is a backport of the Python 3 code with a little bit of additional
information returned to enable Jedi to make decisions.
"""
import types
from jedi import debug
_sentinel = object()

def getattr_static(obj, attr, default=_sentinel):
    """Retrieve attributes without triggering dynamic lookup via the
       descriptor protocol,  __getattr__ or __getattribute__.

       Note: this function may not be able to retrieve all attributes
       that getattr can fetch (like dynamically created attributes)
       and may find attributes that getattr can't (like descriptors
       that raise AttributeError). It can also return descriptor objects
       instead of instance members in some cases. See the
       documentation for details.

       Returns a tuple `(attr, is_get_descriptor)`. is_get_descripter means that
       the attribute is a descriptor that has a `__get__` attribute.
    """
    instance_dict = {}
    klass = None
    if hasattr(obj, '__dict__') and isinstance(obj.__dict__, dict):
        instance_dict = obj.__dict__
    if not isinstance(obj, type):
        klass = type(obj)
        if klass is object:
            klass = None
    
    # Check if the attribute exists in the instance dictionary
    if attr in instance_dict:
        return (instance_dict[attr], False)
    
    # Check if the attribute exists in the class or its bases
    if klass is not None:
        for base in klass.__mro__:
            if attr in base.__dict__:
                value = base.__dict__[attr]
                if hasattr(value, '__get__'):
                    return (value, True)
                return (value, False)
    
    # Check if the object itself is a class
    if isinstance(obj, type):
        for base in obj.__mro__:
            if attr in base.__dict__:
                value = base.__dict__[attr]
                if hasattr(value, '__get__'):
                    return (value, True)
                return (value, False)
    
    # If the attribute is not found and a default is provided, return it
    if default is not _sentinel:
        return (default, False)
    
    # If the attribute is not found and no default is provided, raise AttributeError
    raise AttributeError(f"'{type(obj).__name__}' object has no attribute '{attr}'")
