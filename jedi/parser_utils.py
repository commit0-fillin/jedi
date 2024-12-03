import re
import textwrap
from ast import literal_eval
from inspect import cleandoc
from weakref import WeakKeyDictionary
from parso.python import tree
from parso.cache import parser_cache
from parso import split_lines
_EXECUTE_NODES = {'funcdef', 'classdef', 'import_from', 'import_name', 'test', 'or_test', 'and_test', 'not_test', 'comparison', 'expr', 'xor_expr', 'and_expr', 'shift_expr', 'arith_expr', 'atom_expr', 'term', 'factor', 'power', 'atom'}
_FLOW_KEYWORDS = ('try', 'except', 'finally', 'else', 'if', 'elif', 'with', 'for', 'while')

def get_executable_nodes(node, last_added=False):
    """
    For static analysis.
    """
    result = []
    typ = node.type
    if typ in _EXECUTE_NODES:
        result.append(node)
    if typ == 'suite':
        if not last_added:
            result += node.children[:-1]
        else:
            result += node.children
    elif node.children:
        for child in node.children:
            result += get_executable_nodes(child, last_added)
    return result

def for_stmt_defines_one_name(for_stmt):
    """
    Returns True if only one name is returned: ``for x in y``.
    Returns False if the for loop is more complicated: ``for x, z in y``.

    :returns: bool
    """
    return len(for_stmt.get_defined_names()) == 1

def clean_scope_docstring(scope_node):
    """ Returns a cleaned version of the docstring token. """
    if scope_node.type in ('file_input', 'classdef', 'funcdef'):
        node = scope_node.children[scope_node.children.index(':') + 1]
        if node.type == 'suite':
            first_node = node.children[1]
        else:
            first_node = node
        if first_node.type == 'string':
            return cleandoc(literal_eval(first_node.value))
    return ''

def get_signature(funcdef, width=72, call_string=None, omit_first_param=False, omit_return_annotation=False):
    """
    Generate a string signature of a function.

    :param width: Fold lines if a line is longer than this value.
    :type width: int
    :arg func_name: Override function name when given.
    :type func_name: str

    :rtype: str
    """
    params = funcdef.get_params()
    if omit_first_param:
        params = params[1:]
    
    def param_str(p):
        if p.star_count:
            return ('*' * p.star_count) + p.name.value
        if p.default:
            return f"{p.name.value}={p.default.get_code()}"
        return p.name.value

    param_strs = [param_str(p) for p in params]
    func_name = call_string or funcdef.name.value
    sig = f"{func_name}({', '.join(param_strs)})"
    
    if not omit_return_annotation and funcdef.annotation:
        sig += f" -> {funcdef.annotation.get_code().strip()}"
    
    if len(sig) > width:
        sig = f"{func_name}(\n    " + ",\n    ".join(param_strs) + "\n)"
    
    return sig

def move(node, line_offset):
    """
    Move the `Node` start_pos.
    """
    try:
        children = node.children
    except AttributeError:
        node.line += line_offset
    else:
        for child in children:
            move(child, line_offset)

    try:
        node.start_pos = node.start_pos[0] + line_offset, node.start_pos[1]
    except AttributeError:
        pass

def get_following_comment_same_line(node):
    """
    returns (as string) any comment that appears on the same line,
    after the node, including the #
    """
    try:
        if node.type == 'endmarker':
            return None
        else:
            next_leaf = node.get_next_leaf()
        if next_leaf.type == 'comment' and next_leaf.start_pos[0] == node.end_pos[0]:
            return next_leaf.value
    except AttributeError:
        pass
    return None

def get_parent_scope(node, include_flows=False):
    """
    Returns the underlying scope.
    """
    scope = node.parent
    while scope is not None:
        if scope.type in ('classdef', 'funcdef', 'file_input'):
            return scope
        if include_flows and scope.type in _FLOW_KEYWORDS:
            return scope
        scope = scope.parent
    return None
get_cached_parent_scope = _get_parent_scope_cache(get_parent_scope)

def get_cached_code_lines(grammar, path):
    """
    Basically access the cached code lines in parso. This is not the nicest way
    to do this, but we avoid splitting all the lines again.
    """
    module_node = get_parso_cache_node(grammar, path)
    if module_node is None:
        return None
    return split_lines(module_node.get_code())

def get_parso_cache_node(grammar, path):
    """
    This is of course not public. But as long as I control parso, this
    shouldn't be a problem. ~ Dave

    The reason for this is mostly caching. This is obviously also a sign of a
    broken caching architecture.
    """
    return parser_cache[grammar._hashed][path]

def cut_value_at_position(leaf, position):
    """
    Cuts of the value of the leaf at position
    """
    if leaf.type == 'string':
        matches = re.finditer(r'("""|"|\'\'\'|\').*?\1', leaf.value)
        for match in matches:
            if match.start() <= position[1] <= match.end():
                return leaf.value[:position[1] - leaf.start_pos[1]]
    return leaf.value[:position[1] - leaf.start_pos[1]]

def expr_is_dotted(node):
    """
    Checks if a path looks like `name` or `name.foo.bar` and not `name()`.
    """
    if node.type == 'name':
        return True
    if node.type == 'atom_expr':
        if len(node.children) > 1 and node.children[1].type == 'trailer':
            first_trailer = node.children[1]
            return first_trailer.children[0].type == '.'
    return False
function_is_staticmethod = _function_is_x_method('staticmethod')
function_is_classmethod = _function_is_x_method('classmethod')
function_is_property = _function_is_x_method('property', 'cached_property')
