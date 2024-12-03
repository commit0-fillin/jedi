from collections import defaultdict
from inspect import Parameter
from jedi import debug
from jedi.inference.utils import PushBackIterator
from jedi.inference import analysis
from jedi.inference.lazy_value import LazyKnownValue, LazyTreeValue, LazyUnknownValue
from jedi.inference.value import iterable
from jedi.inference.names import ParamName

class ExecutedParamName(ParamName):

    def __init__(self, function_value, arguments, param_node, lazy_value, is_default=False):
        super().__init__(function_value, param_node.name, arguments=arguments)
        self._lazy_value = lazy_value
        self._is_default = is_default

    def __repr__(self):
        return '<%s: %s>' % (self.__class__.__name__, self.string_name)

def get_executed_param_names_and_issues(function_value, arguments):
    """
    Return a tuple of:
      - a list of `ExecutedParamName`s corresponding to the arguments of the
        function execution `function_value`, containing the inferred value of
        those arguments (whether explicit or default)
      - a list of the issues encountered while building that list

    For example, given:
    ```
    def foo(a, b, c=None, d='d'): ...

    foo(42, c='c')
    ```

    Then for the execution of `foo`, this will return a tuple containing:
      - a list with entries for each parameter a, b, c & d; the entries for a,
        c, & d will have their values (42, 'c' and 'd' respectively) included.
      - a list with a single entry about the lack of a value for `b`
    """
    executed_param_names = []
    issues = []
    
    param_names = function_value.get_param_names()
    
    for param in param_names:
        if param.string_name in arguments.unbound_args:
            value = arguments.unbound_args[param.string_name]
            executed_param_names.append(ExecutedParamName(function_value, arguments, param.tree_name, value))
        elif param.has_default():
            value = param.infer_default()
            executed_param_names.append(ExecutedParamName(function_value, arguments, param.tree_name, value, is_default=True))
        else:
            issues.append(analysis.Error(
                'type-error-too-few-arguments',
                'Missing argument for parameter: ' + param.string_name,
                param.start_pos
            ))
    
    return executed_param_names, issues

def get_executed_param_names(function_value, arguments):
    """
    Return a list of `ExecutedParamName`s corresponding to the arguments of the
    function execution `function_value`, containing the inferred value of those
    arguments (whether explicit or default). Any issues building this list (for
    example required arguments which are missing in the invocation) are ignored.

    For example, given:
    ```
    def foo(a, b, c=None, d='d'): ...

    foo(42, c='c')
    ```

    Then for the execution of `foo`, this will return a list containing entries
    for each parameter a, b, c & d; the entries for a, c, & d will have their
    values (42, 'c' and 'd' respectively) included.
    """
    executed_param_names = []
    
    param_names = function_value.get_param_names()
    
    for param in param_names:
        if param.string_name in arguments.unbound_args:
            value = arguments.unbound_args[param.string_name]
            executed_param_names.append(ExecutedParamName(function_value, arguments, param.tree_name, value))
        elif param.has_default():
            value = param.infer_default()
            executed_param_names.append(ExecutedParamName(function_value, arguments, param.tree_name, value, is_default=True))
        else:
            # For missing required arguments, we create an ExecutedParamName with a None value
            executed_param_names.append(ExecutedParamName(function_value, arguments, param.tree_name, NO_VALUES))
    
    return executed_param_names
