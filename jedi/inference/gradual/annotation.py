"""
PEP 0484 ( https://www.python.org/dev/peps/pep-0484/ ) describes type hints
through function annotations. There is a strong suggestion in this document
that only the type of type hinting defined in PEP0484 should be allowed
as annotations in future python versions.
"""
import re
from inspect import Parameter
from parso import ParserSyntaxError, parse
from jedi.inference.cache import inference_state_method_cache
from jedi.inference.base_value import ValueSet, NO_VALUES
from jedi.inference.gradual.base import DefineGenericBaseClass, GenericClass
from jedi.inference.gradual.generics import TupleGenericManager
from jedi.inference.gradual.type_var import TypeVar
from jedi.inference.helpers import is_string
from jedi.inference.compiled import builtin_from_name
from jedi.inference.param import get_executed_param_names
from jedi import debug
from jedi import parser_utils

def infer_annotation(context, annotation):
    """
    Inferes an annotation node. This means that it inferes the part of
    `int` here:

        foo: int = 3

    Also checks for forward references (strings)
    """
    from jedi.inference.gradual.typing import GenericClass

    def infer():
        if annotation.type == 'string':
            annotation_str = context.inference_state.compiled_subprocess.safe_literal_eval(annotation.value)
            return context.inference_state.parse_and_infer(
                annotation_str,
                context=context,
                node=annotation
            ).execute_annotation()
        else:
            return context.infer_node(annotation)

    value_set = infer()
    if len(value_set) == 1:
        value, = value_set
        if isinstance(value, GenericClass):
            return value.define_generics(value.get_generics())
    return value_set

def _split_comment_param_declaration(decl_text):
    """
    Split decl_text on commas, but group generic expressions
    together.

    For example, given "foo, Bar[baz, biz]" we return
    ['foo', 'Bar[baz, biz]'].

    """
    params = []
    try:
        # Allow splitting by commas and parentheses, but only on the
        # top level.
        node = parse(decl_text, version='3.7').children[0]
        if node.type == 'operator' or node.type == 'atom':
            return [decl_text]

        for param in node.children:
            if param.type in ('atom', 'atom_expr'):
                params.append(param.get_code().strip())
    except ParserSyntaxError:
        # If it's not parseable, we just return the original text.
        # This is not perfect but at least it doesn't crash.
        return [decl_text]
    return params

def _infer_param(function_value, param):
    """
    Infers the type of a function parameter, using type annotations.
    """
    annotation = param.annotation
    if annotation is None:
        # Check for annotations in comments
        annotation_comment = param.annotation_string
        if annotation_comment is not None:
            annotation_comment = annotation_comment.lstrip('(').rstrip(')')
            return infer_annotation(function_value.parent_context, annotation_comment)
        return NO_VALUES

    if annotation.type == 'lambdef':
        # Lambdas are allowed to have annotations, but they are not required to.
        return NO_VALUES

    return infer_annotation(function_value.parent_context, annotation)

@inference_state_method_cache()
def infer_return_types(function, arguments):
    """
    Infers the type of a function's return value,
    according to type annotations.
    """
    annotation = function.tree_node.annotation
    if annotation is None:
        # Check for return annotation in function comment
        comment = clean_scope_docstring(function.tree_node)
        match = re.search(r'^:return:(.+)$', comment, re.M)
        if match:
            annotation_string = match.group(1).strip()
            annotation = parse(annotation_string, version='3.7').children[0]

    if annotation is None:
        return NO_VALUES

    context = function.get_default_param_context()
    inferred_annotation = infer_annotation(context, annotation)

    if function.is_coroutine():
        from jedi.inference.gradual.typing import GenericClass
        from jedi.inference.compiled import builtin_from_name
        coroutine = builtin_from_name(context.inference_state, 'coroutine')
        return ValueSet([GenericClass(
            coroutine,
            generics=(inferred_annotation,)
        )])

    return inferred_annotation

def infer_type_vars_for_execution(function, arguments, annotation_dict):
    """
    Some functions use type vars that are not defined by the class, but rather
    only defined in the function. See for example `iter`. In those cases we
    want to:

    1. Search for undefined type vars.
    2. Infer type vars with the execution state we have.
    3. Return the union of all type vars that have been found.
    """
    from jedi.inference.gradual.typing import BaseTypingValue
    from jedi.inference.gradual.type_var import TypeVar

    found_type_vars = {}
    executed_param_names = get_executed_param_names(function, arguments)

    for executed_param_name in executed_param_names:
        p_name = executed_param_name.string_name
        annotation = annotation_dict.get(p_name)
        if annotation is not None:
            annotation_values = annotation.infer()
            for annotation_value in annotation_values:
                if isinstance(annotation_value, BaseTypingValue):
                    type_var_dict = annotation_value.infer_type_vars(executed_param_name.infer())
                    for type_var_name, values in type_var_dict.items():
                        if type_var_name not in found_type_vars:
                            found_type_vars[type_var_name] = NO_VALUES
                        found_type_vars[type_var_name] |= values

    return found_type_vars

def _infer_type_vars_for_callable(arguments, lazy_params):
    """
    Infers type vars for the Calllable class:

        def x() -> Callable[[Callable[..., _T]], _T]: ...
    """
    from jedi.inference.gradual.typing import TypeVar

    type_var_dict = {}
    for executed_param, lazy_param in zip(arguments.unpack(), lazy_params):
        if isinstance(lazy_param, TypeVar):
            type_var_dict[lazy_param.name] = executed_param.infer()

    return type_var_dict

def merge_pairwise_generics(annotation_value, annotated_argument_class):
    """
    Match up the generic parameters from the given argument class to the
    target annotation.

    This walks the generic parameters immediately within the annotation and
    argument's type, in order to determine the concrete values of the
    annotation's parameters for the current case.

    For example, given the following code:

        def values(mapping: Mapping[K, V]) -> List[V]: ...

        for val in values({1: 'a'}):
            val

    Then this function should be given representations of `Mapping[K, V]`
    and `Mapping[int, str]`, so that it can determine that `K` is `int and
    `V` is `str`.

    Note that it is responsibility of the caller to traverse the MRO of the
    argument type as needed in order to find the type matching the
    annotation (in this case finding `Mapping[int, str]` as a parent of
    `Dict[int, str]`).

    Parameters
    ----------

    `annotation_value`: represents the annotation to infer the concrete
        parameter types of.

    `annotated_argument_class`: represents the annotated class of the
        argument being passed to the object annotated by `annotation_value`.
    """
    from jedi.inference.gradual.typing import GenericClass, TypeVar

    if not isinstance(annotation_value, GenericClass):
        return {}

    type_var_dict = {}
    for annotation_param, argument_param in zip(annotation_value.get_generics(), annotated_argument_class.get_generics()):
        if isinstance(annotation_param, TypeVar):
            type_var_dict[annotation_param.name] = argument_param

    return type_var_dict
