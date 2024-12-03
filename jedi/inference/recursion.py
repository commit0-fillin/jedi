"""
Recursions are the recipe of |jedi| to conquer Python code. However, someone
must stop recursions going mad. Some settings are here to make |jedi| stop at
the right time. You can read more about them :ref:`here <settings-recursion>`.

Next to the internal ``jedi.inference.cache`` this module also makes |jedi| not
thread-safe, because ``execution_recursion_decorator`` uses class variables to
count the function calls.

.. _settings-recursion:

Settings
~~~~~~~~~~

Recursion settings are important if you don't want extremely
recursive python code to go absolutely crazy.

The default values are based on experiments while completing the |jedi| library
itself (inception!). But I don't think there's any other Python library that
uses recursion in a similarly extreme way. Completion should also be fast and
therefore the quality might not always be maximal.

.. autodata:: recursion_limit
.. autodata:: total_function_execution_limit
.. autodata:: per_function_execution_limit
.. autodata:: per_function_recursion_limit
"""
from contextlib import contextmanager
from jedi import debug
from jedi.inference.base_value import NO_VALUES
recursion_limit = 15
'\nLike :func:`sys.getrecursionlimit()`, just for |jedi|.\n'
total_function_execution_limit = 200
'\nThis is a hard limit of how many non-builtin functions can be executed.\n'
per_function_execution_limit = 6
'\nThe maximal amount of times a specific function may be executed.\n'
per_function_recursion_limit = 2
'\nA function may not be executed more than this number of times recursively.\n'

class RecursionDetector:

    def __init__(self):
        self.pushed_nodes = []

@contextmanager
def execution_allowed(inference_state, node):
    """
    A decorator to detect recursions in statements. In a recursion a statement
    at the same place, in the same module may not be executed two times.
    """
    detector = inference_state.recursion_detector
    if node in detector.pushed_nodes:
        debug.warning('Recursion detected: %s', node)
        yield False
    else:
        detector.pushed_nodes.append(node)
        try:
            yield True
        finally:
            detector.pushed_nodes.pop()

class ExecutionRecursionDetector:
    """
    Catches recursions of executions.
    """

    def __init__(self, inference_state):
        self._inference_state = inference_state
        self._recursion_level = 0
        self._parent_execution_funcs = []
        self._funcdef_execution_counts = {}
        self._execution_count = 0
