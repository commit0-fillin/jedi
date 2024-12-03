from textwrap import dedent
from parso import split_lines
from jedi import debug
from jedi.api.exceptions import RefactoringError
from jedi.api.refactoring import Refactoring, EXPRESSION_PARTS
from jedi.common import indent_block
from jedi.parser_utils import function_is_classmethod, function_is_staticmethod
_DEFINITION_SCOPES = ('suite', 'file_input')
_VARIABLE_EXCTRACTABLE = EXPRESSION_PARTS + 'atom testlist_star_expr testlist test lambdef lambdef_nocond keyword name number string fstring'.split()

def _is_expression_with_error(nodes):
    """
    Returns a tuple (is_expression, error_string).
    """
    if len(nodes) != 1:
        return False, "Can only extract expressions"
    
    node = nodes[0]
    if node.type in _VARIABLE_EXCTRACTABLE:
        return True, None
    else:
        return False, f"Cannot extract {node.type}"

def _find_nodes(module_node, pos, until_pos):
    """
    Looks up a module and tries to find the appropriate amount of nodes that
    are in there.
    """
    start_leaf = module_node.get_leaf_for_position(pos)
    end_leaf = module_node.get_leaf_for_position(until_pos)
    
    if start_leaf == end_leaf:
        return [start_leaf]
    
    leaves = list(module_node.get_leaves())
    start_index = leaves.index(start_leaf)
    end_index = leaves.index(end_leaf)
    return leaves[start_index:end_index + 1]

def _split_prefix_at(leaf, until_line):
    """
    Returns a tuple of the leaf's prefix, split at the until_line
    position.
    """
    prefix = leaf.prefix
    if not prefix:
        return '', ''
    
    lines = prefix.splitlines(keepends=True)
    if leaf.start_pos[0] == until_line:
        return '', prefix
    
    split_index = until_line - leaf.start_pos[0]
    return ''.join(lines[:split_index]), ''.join(lines[split_index:])

def _get_parent_definition(node):
    """
    Returns the statement where a node is defined.
    """
    while node is not None:
        if node.type in _DEFINITION_SCOPES:
            return node
        node = node.parent
    return None

def _remove_unwanted_expression_nodes(parent_node, pos, until_pos):
    """
    This function makes it so for `1 * 2 + 3` you can extract `2 + 3`, even
    though it is not part of the expression.
    """
    def is_in_range(node):
        return (pos <= node.start_pos and node.end_pos <= until_pos) or \
               (pos < node.end_pos and node.start_pos < until_pos)

    nodes = []
    for node in parent_node.children:
        if is_in_range(node):
            nodes.append(node)
        elif nodes:
            break

    while len(nodes) > 1 and nodes[0].type in ('operator', 'keyword'):
        nodes = nodes[1:]
    while len(nodes) > 1 and nodes[-1].type in ('operator', 'keyword'):
        nodes = nodes[:-1]

    return nodes

def _find_needed_output_variables(context, search_node, at_least_pos, return_variables):
    """
    Searches everything after at_least_pos in a node and checks if any of the
    return_variables are used in there and returns those.
    """
    needed_variables = set()
    for node in search_node.get_root_node().iter_nodes():
        if node.start_pos < at_least_pos:
            continue
        
        for name in node.get_used_names():
            if name.value in return_variables:
                needed_variables.add(name.value)
    
    return list(needed_variables)
