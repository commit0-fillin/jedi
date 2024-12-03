"""
Helpers for the API
"""
import re
from collections import namedtuple
from textwrap import dedent
from itertools import chain
from functools import wraps
from inspect import Parameter
from parso.python.parser import Parser
from parso.python import tree
from jedi.inference.base_value import NO_VALUES
from jedi.inference.syntax_tree import infer_atom
from jedi.inference.helpers import infer_call_of_leaf
from jedi.inference.compiled import get_string_value_set
from jedi.cache import signature_time_cache, memoize_method
from jedi.parser_utils import get_parent_scope
CompletionParts = namedtuple('CompletionParts', ['path', 'has_dot', 'name'])

class OnErrorLeaf(Exception):
    pass

def get_stack_at_position(grammar, code_lines, leaf, pos):
    """
    Returns the possible node names (e.g. import_from, xor_test or yield_stmt).
    """
    module = grammar.parse(''.join(code_lines))
    stack = []

    node = leaf
    while node is not None:
        if node.type != 'error_leaf':
            stack.insert(0, node)
        node = node.parent

    return [n.type for n in stack]

class CallDetails:

    def __init__(self, bracket_leaf, children, position):
        self.bracket_leaf = bracket_leaf
        self._children = children
        self._position = position

def _get_index_and_key(nodes, position):
    """
    Returns the amount of commas and the keyword argument string.
    """
    index = 0
    key = None
    for node in nodes:
        if node.start_pos >= position:
            if node.type == 'argument' and node.children[0].type == 'name':
                key = node.children[0].value
            break
        if node.type == 'operator' and node.value == ',':
            index += 1

    return index, key

@signature_time_cache('call_signatures_validity')
def cache_signatures(inference_state, context, bracket_leaf, code_lines, user_pos):
    """This function calculates the cache key."""
    content = ''.join(code_lines)
    index = bracket_leaf.start_pos[0] - 1
    before_cursor = content[:index]
    other_lines = content[index:].split('\n')
    before_bracket = before_cursor + other_lines[0]
    indent = re.match(r'[ \t]*', other_lines[1]).group(0)
    before_bracket += indent
    return (before_bracket, user_pos[1])

def get_module_names(module, all_scopes, definitions=True, references=False):
    """
    Returns a dictionary with name parts as keys and their call paths as
    values.
    """
    names = {}
    def process_name(name):
        if name.tree_name is not None:
            names.setdefault(name.string_name, []).append(name)

    if definitions:
        module.tree_node.iter_used_names()
    if references:
        module.tree_node.iter_used_names()

    for name_leaf in module.tree_node.get_used_names().values():
        if definitions:
            name = module.create_name(name_leaf)
            process_name(name)
        if references:
            for name in name_leaf.get_definition_names():
                process_name(name)

    return names
