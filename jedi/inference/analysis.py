"""
Module for statical analysis.
"""
from parso.python import tree
from jedi import debug
from jedi.inference.helpers import is_string
CODES = {'attribute-error': (1, AttributeError, 'Potential AttributeError.'), 'name-error': (2, NameError, 'Potential NameError.'), 'import-error': (3, ImportError, 'Potential ImportError.'), 'type-error-too-many-arguments': (4, TypeError, None), 'type-error-too-few-arguments': (5, TypeError, None), 'type-error-keyword-argument': (6, TypeError, None), 'type-error-multiple-values': (7, TypeError, None), 'type-error-star-star': (8, TypeError, None), 'type-error-star': (9, TypeError, None), 'type-error-operation': (10, TypeError, None), 'type-error-not-iterable': (11, TypeError, None), 'type-error-isinstance': (12, TypeError, None), 'type-error-not-subscriptable': (13, TypeError, None), 'value-error-too-many-values': (14, ValueError, None), 'value-error-too-few-values': (15, ValueError, None)}

class Error:

    def __init__(self, name, module_path, start_pos, message=None):
        self.path = module_path
        self._start_pos = start_pos
        self.name = name
        if message is None:
            message = CODES[self.name][2]
        self.message = message

    def __str__(self):
        return '%s:%s:%s: %s %s' % (self.path, self.line, self.column, self.code, self.message)

    def __eq__(self, other):
        return self.path == other.path and self.name == other.name and (self._start_pos == other._start_pos)

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        return hash((self.path, self._start_pos, self.name))

    def __repr__(self):
        return f'<{self.__class__.__name__} {self.name}: {self.path}@{self._start_pos[0]},{self._start_pos[1]}>'

class Warning(Error):
    pass

def _check_for_setattr(instance):
    """
    Check if there's any setattr method inside an instance. If so, return True.
    """
    for name, value in instance.get_filters():
        if name.string_name == 'setattr':
            return True
    return False

def _check_for_exception_catch(node_context, jedi_name, exception, payload=None):
    """
    Checks if a jedi object (e.g. `Statement`) sits inside a try/catch and
    doesn't count as an error (if equal to `exception`).
    Also checks `hasattr` for AttributeErrors and uses the `payload` to compare
    it.
    Returns True if the exception was caught.
    """
    def check_match(except_clause):
        if except_clause is None:
            return False
        except_classes = except_clause.get_except_classes()
        if not except_classes:
            return True  # An empty except catches all exceptions
        for except_class in except_classes:
            if except_class.name.get_qualified_names() == exception.split('.'):
                return True
        return False

    def check_hasattr(node):
        if isinstance(node, tree.Name) and node.value == 'hasattr':
            call = node.parent
            if isinstance(call, tree.PythonNode) and call.type == 'power':
                args = call.children[1].children[1:-1]
                if len(args) == 2 and isinstance(args[1], tree.Name):
                    return args[1].value == payload
        return False

    current = node_context.tree_node
    while current is not None:
        if isinstance(current, tree.TryStmt):
            for except_clause in current.get_except_clauses():
                if check_match(except_clause):
                    return True
        elif exception == 'AttributeError' and check_hasattr(current):
            return True
        current = current.parent

    return False
