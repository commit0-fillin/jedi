"""
There are a couple of classes documented in here:

- :class:`.BaseName` as an abstact base class for almost everything.
- :class:`.Name` used in a lot of places
- :class:`.Completion` for completions
- :class:`.BaseSignature` as a base class for signatures
- :class:`.Signature` for :meth:`.Script.get_signatures` only
- :class:`.ParamName` used for parameters of signatures
- :class:`.Refactoring` for refactorings
- :class:`.SyntaxError` for :meth:`.Script.get_syntax_errors` only

These classes are the much biggest part of the API, because they contain
the interesting information about all operations.
"""
import re
from pathlib import Path
from typing import Optional
from parso.tree import search_ancestor
from jedi import settings
from jedi import debug
from jedi.inference.utils import unite
from jedi.cache import memoize_method
from jedi.inference.compiled.mixed import MixedName
from jedi.inference.names import ImportName, SubModuleName
from jedi.inference.gradual.stub_value import StubModuleValue
from jedi.inference.gradual.conversion import convert_names, convert_values
from jedi.inference.base_value import ValueSet, HasNoContext
from jedi.api.keywords import KeywordName
from jedi.api import completion_cache
from jedi.api.helpers import filter_follow_imports

def defined_names(inference_state, value):
    """
    List sub-definitions (e.g., methods in class).

    :type scope: Scope
    :rtype: list of Name
    """
    pass

class BaseName:
    """
    The base class for all definitions, completions and signatures.
    """
    _mapping = {'posixpath': 'os.path', 'riscospath': 'os.path', 'ntpath': 'os.path', 'os2emxpath': 'os.path', 'macpath': 'os.path', 'genericpath': 'os.path', 'posix': 'os', '_io': 'io', '_functools': 'functools', '_collections': 'collections', '_socket': 'socket', '_sqlite3': 'sqlite3'}
    _tuple_mapping = dict(((tuple(k.split('.')), v) for k, v in {'argparse._ActionsContainer': 'argparse.ArgumentParser'}.items()))

    def __init__(self, inference_state, name):
        self._inference_state = inference_state
        self._name = name
        '\n        An instance of :class:`parso.python.tree.Name` subclass.\n        '
        self.is_keyword = isinstance(self._name, KeywordName)

    @property
    def module_path(self) -> Optional[Path]:
        """
        Shows the file path of a module. e.g. ``/usr/lib/python3.9/os.py``
        """
        if self._name.is_stub():
            return None
        return self._name.get_defining_module().py__file__()

    @property
    def name(self):
        """
        Name of variable/function/class/module.

        For example, for ``x = None`` it returns ``'x'``.

        :rtype: str or None
        """
        return self._name.string_name

    @property
    def type(self):
        """
        The type of the definition.

        Here is an example of the value of this attribute.  Let's consider
        the following source.  As what is in ``variable`` is unambiguous
        to Jedi, :meth:`jedi.Script.infer` should return a list of
        definition for ``sys``, ``f``, ``C`` and ``x``.

        >>> from jedi import Script
        >>> source = '''
        ... import keyword
        ...
        ... class C:
        ...     pass
        ...
        ... class D:
        ...     pass
        ...
        ... x = D()
        ...
        ... def f():
        ...     pass
        ...
        ... for variable in [keyword, f, C, x]:
        ...     variable'''

        >>> script = Script(source)
        >>> defs = script.infer()

        Before showing what is in ``defs``, let's sort it by :attr:`line`
        so that it is easy to relate the result to the source code.

        >>> defs = sorted(defs, key=lambda d: d.line)
        >>> print(defs)  # doctest: +NORMALIZE_WHITESPACE
        [<Name full_name='keyword', description='module keyword'>,
         <Name full_name='__main__.C', description='class C'>,
         <Name full_name='__main__.D', description='instance D'>,
         <Name full_name='__main__.f', description='def f'>]

        Finally, here is what you can get from :attr:`type`:

        >>> defs = [d.type for d in defs]
        >>> defs[0]
        'module'
        >>> defs[1]
        'class'
        >>> defs[2]
        'instance'
        >>> defs[3]
        'function'

        Valid values for type are ``module``, ``class``, ``instance``, ``function``,
        ``param``, ``path``, ``keyword``, ``property`` and ``statement``.

        """
        if isinstance(self._name, ImportName):
            return 'module'
        definition = self._name.get_definition()
        if definition is None:
            return None

        return self._API_TYPES.get(definition.type, 'statement')

    @property
    def module_name(self):
        """
        The module name, a bit similar to what ``__name__`` is in a random
        Python module.

        >>> from jedi import Script
        >>> source = 'import json'
        >>> script = Script(source, path='example.py')
        >>> d = script.infer()[0]
        >>> print(d.module_name)  # doctest: +ELLIPSIS
        json
        """
        pass

    def in_builtin_module(self):
        """
        Returns True, if this is a builtin module.
        """
        pass

    @property
    def line(self):
        """The line where the definition occurs (starting with 1)."""
        pass

    @property
    def column(self):
        """The column where the definition occurs (starting with 0)."""
        pass

    def get_definition_start_position(self):
        """
        The (row, column) of the start of the definition range. Rows start with
        1, columns start with 0.

        :rtype: Optional[Tuple[int, int]]
        """
        pass

    def get_definition_end_position(self):
        """
        The (row, column) of the end of the definition range. Rows start with
        1, columns start with 0.

        :rtype: Optional[Tuple[int, int]]
        """
        pass

    def docstring(self, raw=False, fast=True):
        """
        Return a document string for this completion object.

        Example:

        >>> from jedi import Script
        >>> source = '''\\
        ... def f(a, b=1):
        ...     "Document for function f."
        ... '''
        >>> script = Script(source, path='example.py')
        >>> doc = script.infer(1, len('def f'))[0].docstring()
        >>> print(doc)
        f(a, b=1)
        <BLANKLINE>
        Document for function f.

        Notice that useful extra information is added to the actual
        docstring, e.g. function signatures are prepended to their docstrings.
        If you need the actual docstring, use ``raw=True`` instead.

        >>> print(script.infer(1, len('def f'))[0].docstring(raw=True))
        Document for function f.

        :param fast: Don't follow imports that are only one level deep like
            ``import foo``, but follow ``from foo import bar``. This makes
            sense for speed reasons. Completing `import a` is slow if you use
            the ``foo.docstring(fast=False)`` on every object, because it
            parses all libraries starting with ``a``.
        """
        pass

    @property
    def description(self):
        """
        A description of the :class:`.Name` object, which is heavily used
        in testing. e.g. for ``isinstance`` it returns ``def isinstance``.

        Example:

        >>> from jedi import Script
        >>> source = '''
        ... def f():
        ...     pass
        ...
        ... class C:
        ...     pass
        ...
        ... variable = f if random.choice([0,1]) else C'''
        >>> script = Script(source)  # line is maximum by default
        >>> defs = script.infer(column=3)
        >>> defs = sorted(defs, key=lambda d: d.line)
        >>> print(defs)  # doctest: +NORMALIZE_WHITESPACE
        [<Name full_name='__main__.f', description='def f'>,
         <Name full_name='__main__.C', description='class C'>]
        >>> str(defs[0].description)
        'def f'
        >>> str(defs[1].description)
        'class C'

        """
        pass

    @property
    def full_name(self):
        """
        Dot-separated path of this object.

        It is in the form of ``<module>[.<submodule>[...]][.<object>]``.
        It is useful when you want to look up Python manual of the
        object at hand.

        Example:

        >>> from jedi import Script
        >>> source = '''
        ... import os
        ... os.path.join'''
        >>> script = Script(source, path='example.py')
        >>> print(script.infer(3, len('os.path.join'))[0].full_name)
        os.path.join

        Notice that it returns ``'os.path.join'`` instead of (for example)
        ``'posixpath.join'``. This is not correct, since the modules name would
        be ``<module 'posixpath' ...>```. However most users find the latter
        more practical.
        """
        pass

    def is_stub(self):
        """
        Returns True if the current name is defined in a stub file.
        """
        pass

    def is_side_effect(self):
        """
        Checks if a name is defined as ``self.foo = 3``. In case of self, this
        function would return False, for foo it would return True.
        """
        pass

    @debug.increase_indent_cm('goto on name')
    def goto(self, *, follow_imports=False, follow_builtin_imports=False, only_stubs=False, prefer_stubs=False):
        """
        Like :meth:`.Script.goto` (also supports the same params), but does it
        for the current name. This is typically useful if you are using
        something like :meth:`.Script.get_names()`.

        :param follow_imports: The goto call will follow imports.
        :param follow_builtin_imports: If follow_imports is True will try to
            look up names in builtins (i.e. compiled or extension modules).
        :param only_stubs: Only return stubs for this goto call.
        :param prefer_stubs: Prefer stubs to Python objects for this goto call.
        :rtype: list of :class:`Name`
        """
        pass

    @debug.increase_indent_cm('infer on name')
    def infer(self, *, only_stubs=False, prefer_stubs=False):
        """
        Like :meth:`.Script.infer`, it can be useful to understand which type
        the current name has.

        Return the actual definitions. I strongly recommend not using it for
        your completions, because it might slow down |jedi|. If you want to
        read only a few objects (<=20), it might be useful, especially to get
        the original docstrings. The basic problem of this function is that it
        follows all results. This means with 1000 completions (e.g.  numpy),
        it's just very, very slow.

        :param only_stubs: Only return stubs for this goto call.
        :param prefer_stubs: Prefer stubs to Python objects for this type
            inference call.
        :rtype: list of :class:`Name`
        """
        pass

    def parent(self):
        """
        Returns the parent scope of this identifier.

        :rtype: Name
        """
        pass

    def __repr__(self):
        return '<%s %sname=%r, description=%r>' % (self.__class__.__name__, 'full_' if self.full_name else '', self.full_name or self.name, self.description)

    def get_line_code(self, before=0, after=0):
        """
        Returns the line of code where this object was defined.

        :param before: Add n lines before the current line to the output.
        :param after: Add n lines after the current line to the output.

        :return str: Returns the line(s) of code or an empty string if it's a
                     builtin.
        """
        pass

    def get_signatures(self):
        """
        Returns all potential signatures for a function or a class. Multiple
        signatures are typical if you use Python stubs with ``@overload``.

        :rtype: list of :class:`BaseSignature`
        """
        pass

    def execute(self):
        """
        Uses type inference to "execute" this identifier and returns the
        executed objects.

        :rtype: list of :class:`Name`
        """
        pass

    def get_type_hint(self):
        """
        Returns type hints like ``Iterable[int]`` or ``Union[int, str]``.

        This method might be quite slow, especially for functions. The problem
        is finding executions for those functions to return something like
        ``Callable[[int, str], str]``.

        :rtype: str
        """
        pass

class Completion(BaseName):
    """
    ``Completion`` objects are returned from :meth:`.Script.complete`. They
    provide additional information about a completion.
    """

    def __init__(self, inference_state, name, stack, like_name_length, is_fuzzy, cached_name=None):
        super().__init__(inference_state, name)
        self._like_name_length = like_name_length
        self._stack = stack
        self._is_fuzzy = is_fuzzy
        self._cached_name = cached_name
        self._same_name_completions = []

    @property
    def complete(self):
        """
        Only works with non-fuzzy completions. Returns None if fuzzy
        completions are used.

        Return the rest of the word, e.g. completing ``isinstance``::

            isinstan# <-- Cursor is here

        would return the string 'ce'. It also adds additional stuff, depending
        on your ``settings.py``.

        Assuming the following function definition::

            def foo(param=0):
                pass

        completing ``foo(par`` would give a ``Completion`` which ``complete``
        would be ``am=``.
        """
        pass

    @property
    def name_with_symbols(self):
        """
        Similar to :attr:`.name`, but like :attr:`.name` returns also the
        symbols, for example assuming the following function definition::

            def foo(param=0):
                pass

        completing ``foo(`` would give a ``Completion`` which
        ``name_with_symbols`` would be "param=".

        """
        pass

    def docstring(self, raw=False, fast=True):
        """
        Documented under :meth:`BaseName.docstring`.
        """
        pass

    @property
    def type(self):
        """
        Documented under :meth:`BaseName.type`.
        """
        pass

    def get_completion_prefix_length(self):
        """
        Returns the length of the prefix being completed.
        For example, completing ``isinstance``::

            isinstan# <-- Cursor is here

        would return 8, because len('isinstan') == 8.

        Assuming the following function definition::

            def foo(param=0):
                pass

        completing ``foo(par`` would return 3.
        """
        pass

    def __repr__(self):
        return '<%s: %s>' % (type(self).__name__, self._name.get_public_name())

class Name(BaseName):
    """
    *Name* objects are returned from many different APIs including
    :meth:`.Script.goto` or :meth:`.Script.infer`.
    """

    def __init__(self, inference_state, definition):
        super().__init__(inference_state, definition)

    @memoize_method
    def defined_names(self):
        """
        List sub-definitions (e.g., methods in class).

        :rtype: list of :class:`Name`
        """
        return defined_names(self._inference_state, self._value)

    def is_definition(self):
        """
        Returns True, if defined as a name in a statement, function or class.
        Returns False, if it's a reference to such a definition.
        """
        pass

    def __eq__(self, other):
        return self._name.start_pos == other._name.start_pos and self.module_path == other.module_path and (self.name == other.name) and (self._inference_state == other._inference_state)

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        return hash((self._name.start_pos, self.module_path, self.name, self._inference_state))

class BaseSignature(Name):
    """
    These signatures are returned by :meth:`BaseName.get_signatures`
    calls.
    """

    def __init__(self, inference_state, signature):
        super().__init__(inference_state, signature.name)
        self._signature = signature

    @property
    def params(self):
        """
        Returns definitions for all parameters that a signature defines.
        This includes stuff like ``*args`` and ``**kwargs``.

        :rtype: list of :class:`.ParamName`
        """
        pass

    def to_string(self):
        """
        Returns a text representation of the signature. This could for example
        look like ``foo(bar, baz: int, **kwargs)``.

        :rtype: str
        """
        pass

class Signature(BaseSignature):
    """
    A full signature object is the return value of
    :meth:`.Script.get_signatures`.
    """

    def __init__(self, inference_state, signature, call_details):
        super().__init__(inference_state, signature)
        self._call_details = call_details
        self._signature = signature

    @property
    def index(self):
        """
        Returns the param index of the current cursor position.
        Returns None if the index cannot be found in the curent call.

        :rtype: int
        """
        pass

    @property
    def bracket_start(self):
        """
        Returns a line/column tuple of the bracket that is responsible for the
        last function call. The first line is 1 and the first column 0.

        :rtype: int, int
        """
        pass

    def __repr__(self):
        return '<%s: index=%r %s>' % (type(self).__name__, self.index, self._signature.to_string())

class ParamName(Name):

    def infer_default(self):
        """
        Returns default values like the ``1`` of ``def foo(x=1):``.

        :rtype: list of :class:`.Name`
        """
        pass

    def infer_annotation(self, **kwargs):
        """
        :param execute_annotation: Default True; If False, values are not
            executed and classes are returned instead of instances.
        :rtype: list of :class:`.Name`
        """
        pass

    def to_string(self):
        """
        Returns a simple representation of a param, like
        ``f: Callable[..., Any]``.

        :rtype: str
        """
        pass

    @property
    def kind(self):
        """
        Returns an enum instance of :mod:`inspect`'s ``Parameter`` enum.

        :rtype: :py:attr:`inspect.Parameter.kind`
        """
        pass
