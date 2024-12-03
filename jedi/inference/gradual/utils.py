from pathlib import Path
from jedi.inference.gradual.typeshed import TYPESHED_PATH, create_stub_module
from jedi.inference.base_value import ValueSet, NO_VALUES
from jedi.inference.gradual.typeshed import _try_to_load_stub

def load_proper_stub_module(inference_state, grammar, file_io, import_names, module_node):
    """
    This function is given a random .pyi file and should return the proper
    module.
    """
    # First, try to load the stub using the _try_to_load_stub function
    stub_module = _try_to_load_stub(
        inference_state,
        import_names,
        ValueSet([]),  # We don't have a python_value_set here
        None,  # We don't have a parent_module_value here
        inference_state.get_sys_path()
    )

    if stub_module != NO_VALUES:
        return stub_module.get_first_non_filtered_value()

    # If no stub is found, create a new stub module
    stub_module = create_stub_module(
        inference_state,
        file_io.path,
        module_node,
        ValueSet([]),  # We don't have a python_value_set here
        None  # We don't have a parent_module_value here
    )

    return stub_module
