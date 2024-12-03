"""
Functions inferring the syntax tree.
"""
import copy
import itertools
from parso.python import tree
from jedi import debug
from jedi import parser_utils
from jedi.inference.base_value import ValueSet, NO_VALUES, ContextualizedNode, iterator_to_value_set, iterate_values
from jedi.inference.lazy_value import LazyTreeValue
from jedi.inference import compiled
from jedi.inference import recursion
from jedi.inference import analysis
from jedi.inference import imports
from jedi.inference import arguments
from jedi.inference.value import ClassValue, FunctionValue
from jedi.inference.value import iterable
from jedi.inference.value.dynamic_arrays import ListModification, DictModification
from jedi.inference.value import TreeInstance
from jedi.inference.helpers import is_string, is_literal, is_number, get_names_of_node, is_big_annoying_library
from jedi.inference.compiled.access import COMPARISON_OPERATORS
from jedi.inference.cache import inference_state_method_cache
from jedi.inference.gradual.stub_value import VersionInfo
from jedi.inference.gradual import annotation
from jedi.inference.names import TreeNameDefinition
from jedi.inference.context import CompForContext
from jedi.inference.value.decorator import Decoratee
from jedi.plugins import plugin_manager
operator_to_magic_method = {'+': '__add__', '-': '__sub__', '*': '__mul__', '@': '__matmul__', '/': '__truediv__', '//': '__floordiv__', '%': '__mod__', '**': '__pow__', '<<': '__lshift__', '>>': '__rshift__', '&': '__and__', '|': '__or__', '^': '__xor__'}
reverse_operator_to_magic_method = {k: '__r' + v[2:] for k, v in operator_to_magic_method.items()}

def _limit_value_infers(func):
    """
    This is for now the way how we limit type inference going wild. There are
    other ways to ensure recursion limits as well. This is mostly necessary
    because of instance (self) access that can be quite tricky to limit.

    I'm still not sure this is the way to go, but it looks okay for now and we
    can still go anther way in the future. Tests are there. ~ dave
    """
    def wrapper(*args, **kwargs):
        inference_state = args[0].inference_state
        with recursion.execution_allowed(inference_state, node=args[1]) as allowed:
            if allowed:
                return func(*args, **kwargs)
            return NO_VALUES
    return wrapper

def _infer_node_if_inferred(context, element):
    """
    TODO This function is temporary: Merge with infer_node.
    """
    if element.type in ('name', 'atom_expr', 'power'):
        return context.infer_node(element)
    return infer_node(context, element)

def infer_atom(context, atom):
    """
    Basically to process ``atom`` nodes. The parser sometimes doesn't
    generate the node (because it has just one child). In that case an atom
    might be a name or a literal as well.
    """
    if atom.type == 'atom':
        first_child = atom.children[0]
        if first_child.type in ('string', 'number', 'keyword'):
            return infer_node(context, first_child)
        elif first_child == '[':
            return infer_node(context, atom.children[1])
        elif first_child == '{':
            return infer_node(context, atom.children[1])
        elif first_child == '(':
            return infer_node(context, atom.children[1])
    elif atom.type in ('name', 'number', 'string', 'keyword'):
        return infer_node(context, atom)
    return NO_VALUES

@debug.increase_indent
def _infer_expr_stmt(context, stmt, seek_name=None):
    """
    The starting point of the completion. A statement always owns a call
    list, which are the calls, that a statement does. In case multiple
    names are defined in the statement, `seek_name` returns the result for
    this name.

    expr_stmt: testlist_star_expr (annassign | augassign (yield_expr|testlist) |
                     ('=' (yield_expr|testlist_star_expr))*)
    annassign: ':' test ['=' test]
    augassign: ('+=' | '-=' | '*=' | '@=' | '/=' | '%=' | '&=' | '|=' | '^=' |
                '<<=' | '>>=' | '**=' | '//=')

    :param stmt: A `tree.ExprStmt`.
    """
    first_operator = next((c for c in stmt.children if c in ('=', '+=', '-=', '*=', '@=', '/=', '%=', '&=', '|=', '^=', '<<=', '>>=', '**=', '//=')), None)
    if first_operator is None:
        return _infer_node_if_inferred(context, stmt.children[0])

    if first_operator == '=':
        lhs = stmt.children[0]
        rhs = stmt.children[2]
        if seek_name is not None:
            if seek_name.value in get_names_of_node(lhs):
                return _infer_node_if_inferred(context, rhs)
        else:
            return _infer_node_if_inferred(context, rhs)
    else:  # augassign
        lhs = stmt.children[0]
        rhs = stmt.children[2]
        if seek_name is not None and seek_name.value in get_names_of_node(lhs):
            operator = first_operator[:-1]  # Remove the '=' at the end
            lhs_values = context.infer_node(lhs)
            rhs_values = context.infer_node(rhs)
            return _eval_comparison(context, lhs_values, operator, rhs_values)

    return NO_VALUES

@iterator_to_value_set
def infer_factor(value_set, operator):
    """
    Calculates `+`, `-`, `~` and `not` prefixes.
    """
    for value in value_set:
        if operator == '+':
            yield value
        elif operator == '-':
            if is_number(value):
                yield value.negate()
        elif operator == '~':
            if is_number(value):
                yield value.bitwise_not()
        elif operator == 'not':
            yield compiled.create_simple_object(value.inference_state, not value.py__bool__())

@inference_state_method_cache()
def _apply_decorators(context, node):
    """
    Returns the function, that should to be executed in the end.
    This is also the places where the decorators are processed.
    """
    if node.type != 'funcdef':
        return context.infer_node(node)

    decorators = node.get_decorators()
    if not decorators:
        return context.infer_node(node)

    function_execution = context.infer_node(node)
    for decorator in reversed(decorators):
        decorator_values = context.infer_node(decorator.children[1])
        if not decorator_values:
            debug.warning('Decorator not found: %s', decorator)
            continue
        function_execution = ValueSet.from_sets(
            _execute_decorated_function(context, function_execution, decorator_value)
            for decorator_value in decorator_values
        )
    return function_execution

def check_tuple_assignments(name, value_set):
    """
    Checks if tuples are assigned.
    """
    for index, node in name.assignment_indexes():
        values = iterate_values(value_set)
        for value in values:
            try:
                value = value.get_item(index)
            except IndexError:
                continue
            yield value

class ContextualizedSubscriptListNode(ContextualizedNode):
    pass

def _infer_subscript_list(context, index):
    """
    Handles slices in subscript nodes.
    """
    if index == ':':
        return ValueSet([iterable.Slice(context.inference_state, None, None, None)])

    elif index.type == 'subscript' and not index.children[0] == '.':
        start, stop, step = None, None, None
        result = []
        for el in index.children:
            if el == ':':
                if not result:
                    result.append(iterable.Slice(context.inference_state, start, stop, step))
            elif el.type == 'sliceop':
                step = el.children[1]
            else:
                result.append(context.infer_node(el))
        if result:
            return ValueSet(result)
    else:
        return context.infer_node(index)

    return NO_VALUES
