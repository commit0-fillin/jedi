def import_module(callback):
    """
    Handle "magic" Flask extension imports:
    ``flask.ext.foo`` is really ``flask_foo`` or ``flaskext.foo``.
    """
    def wrapper(inference_state, import_names, module_context, *args, **kwargs):
        if import_names[:2] == ('flask', 'ext'):
            # Try flask_foo
            new_import_names = ('flask_' + import_names[2],) + import_names[3:]
            module = callback(inference_state, new_import_names, module_context, *args, **kwargs)
            if module:
                return module

            # Try flaskext.foo
            new_import_names = ('flaskext',) + import_names[2:]
            return callback(inference_state, new_import_names, module_context, *args, **kwargs)

        # For all other imports, use the original callback
        return callback(inference_state, import_names, module_context, *args, **kwargs)

    return wrapper
