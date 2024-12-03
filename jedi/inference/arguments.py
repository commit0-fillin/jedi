import re
from itertools import zip_longest
from parso.python import tree
from jedi import debug
from jedi.inference.utils import PushBackIterator
from jedi.inference import analysis
from jedi.inference.lazy_value import LazyKnownValue, LazyKnownValues, LazyTreeValue, get_merged_lazy_value
from jedi.inference.names import ParamName, TreeNameDefinition, AnonymousParamName
from jedi.inference.base_value import NO_VALUES, ValueSet, ContextualizedNode
from jedi.inference.value import iterable
from jedi.inference.cache import inference_state_as_method_param_cache

def try_iter_content(types, depth=0):
    """Helper method for static analysis."""
    if depth > 10:
        # Prevent infinite recursion
        return
    
    for typ in types:
        try:
            for lazy_value in typ.py__iter__():
                yield from try_iter_content(lazy_value.infer(), depth + 1)
        except AttributeError:
            yield typ

class ParamIssue(Exception):
    pass

def repack_with_argument_clinic(clinic_string):
    """
    Transforms a function or method with arguments to the signature that is
    given as an argument clinic notation.

    Argument clinic is part of CPython and used for all the functions that are
    implemented in C (Python 3.7):

        str.split.__text_signature__
        # Results in: '($self, /, sep=None, maxsplit=-1)'
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            # Parse the clinic string
            params = re.findall(r'(\w+)(?:=([^,\)]+))?', clinic_string)
            
            # Repack arguments according to the clinic string
            new_args = []
            new_kwargs = {}
            
            for i, (param, default) in enumerate(params):
                if i < len(args):
                    new_args.append(args[i])
                elif param in kwargs:
                    new_kwargs[param] = kwargs[param]
                elif default:
                    new_kwargs[param] = eval(default)
                else:
                    raise TypeError(f"Missing required argument: {param}")
            
            return func(*new_args, **new_kwargs)
        return wrapper
    return decorator

def iterate_argument_clinic(inference_state, arguments, clinic_string):
    """Uses a list with argument clinic information (see PEP 436)."""
    params = re.findall(r'(\w+)(?:=([^,\)]+))?', clinic_string)
    arg_iterator = PushBackIterator(arguments)

    for param, default in params:
        try:
            arg = next(arg_iterator)
            yield param, LazyTreeValue(inference_state, arg)
        except StopIteration:
            if default:
                yield param, LazyKnownValue(eval(default))
            else:
                raise ParamIssue(f"Missing required argument: {param}")

    # Check for extra arguments
    try:
        extra = next(arg_iterator)
        raise ParamIssue(f"Too many arguments provided. Unexpected: {extra}")
    except StopIteration:
        pass

class _AbstractArgumentsMixin:
    pass

class AbstractArguments(_AbstractArgumentsMixin):
    context = None
    argument_node = None
    trailer = None

class TreeArguments(AbstractArguments):

    def __init__(self, inference_state, context, argument_node, trailer=None):
        """
        :param argument_node: May be an argument_node or a list of nodes.
        """
        self.argument_node = argument_node
        self.context = context
        self._inference_state = inference_state
        self.trailer = trailer

    def __repr__(self):
        return '<%s: %s>' % (self.__class__.__name__, self.argument_node)

class ValuesArguments(AbstractArguments):

    def __init__(self, values_list):
        self._values_list = values_list

    def __repr__(self):
        return '<%s: %s>' % (self.__class__.__name__, self._values_list)

class TreeArgumentsWrapper(_AbstractArgumentsMixin):

    def __init__(self, arguments):
        self._wrapped_arguments = arguments

    def __repr__(self):
        return '<%s: %s>' % (self.__class__.__name__, self._wrapped_arguments)
