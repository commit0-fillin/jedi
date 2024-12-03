import copy
import sys
import re
import os
from itertools import chain
from contextlib import contextmanager
from parso.python import tree

def deep_ast_copy(obj):
    """
    Much, much faster than copy.deepcopy, but just for parser tree nodes.
    """
    if isinstance(obj, tree.BaseNode):
        new_child = copy.copy(obj)
        new_child.children = [deep_ast_copy(child) for child in obj.children]
        return new_child
    elif isinstance(obj, list):
        return [deep_ast_copy(element) for element in obj]
    else:
        return obj

def infer_call_of_leaf(context, leaf, cut_own_trailer=False):
    """
    Creates a "call" node that consist of all ``trailer`` and ``power``
    objects.  E.g. if you call it with ``append``::

        list([]).append(3) or None

    You would get a node with the content ``list([]).append`` back.

    This generates a copy of the original ast node.

    If you're using the leaf, e.g. the bracket `)` it will return ``list([])``.

    We use this function for two purposes. Given an expression ``bar.foo``,
    we may want to
      - infer the type of ``foo`` to offer completions after foo
      - infer the type of ``bar`` to be able to jump to the definition of foo
    The option ``cut_own_trailer`` must be set to true for the second purpose.
    """
    trailer = leaf.parent
    if trailer.type != 'trailer' or trailer.children[0] != '.':
        trailer = None

    power = leaf
    while power.parent is not None and power.parent.type in ('power', 'trailer', 'atom_expr'):
        power = power.parent

    if power.type == 'atom_expr':
        power = deep_ast_copy(power)
    else:
        power = tree.Node('atom_expr', [deep_ast_copy(power)])

    if trailer is not None and cut_own_trailer:
        cut_idx = power.children.index(trailer)
        power.children[cut_idx + 1:] = []

    return context.infer_node(power)

class SimpleGetItemNotFound(Exception):
    pass
