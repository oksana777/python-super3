"""
Super3 is Python 3's super() for Python 2
"""

import sys
import inspect


def find_code_in_classes(classes, code, freevars):
    for cls in classes:
        for attr, value in cls.__dict__.items():
            try:
                if (
                    value.__code__ == code and
                    tuple(cell_contents(value.__closure__)) == freevars
                ):
                    return cls, attr
            except AttributeError:
                continue


def cell_contents(cells):
    try:
        for cell in cells:
            yield cell.cell_contents
    except TypeError:
        pass


class super3(super):
    _cache = {}
    _act_more_like_python3 = True

    def __init__(self, *args, **kwargs):
        type, obj, func_name = self.__args__(*args, **kwargs)
        self.bound_caller_func = getattr(obj, func_name)
        super(super3, self).__init__(type, obj)

    def __new__(cls, *args, **kwargs):
        try:
            return super(super3, cls).__new__(cls, *args)
        # work around for PyPy having a different implementation of super()
        except TypeError:
            type, obj, func_name = cls.__args__(*args, **kwargs)
            new = super(super3, cls).__new__(cls, type, obj)
            new.bound_caller_func = getattr(obj, func_name)
            return new

    @classmethod
    def __args__(cls, *args, **kwargs):
        # Find the caller and work out the class it was defined in (not what it
        # was bound to!) need to f_back's to get out of super3()
        caller = kwargs.get('caller') or sys._getframe().f_back.f_back
        caller_code = caller.f_code

        try:
            caller_self = caller.f_locals[caller.f_code.co_varnames[0]]
        except IndexError:
            # in case self is hidden in varargs
            caller_args = inspect.getargvalues(caller)
            caller_self = caller_args.locals[caller_args.varargs][0]

        caller_name_in_class = caller_name = caller_code.co_name

        # for decorated methods we'll probably need to check the closure
        # vars too to properly distinguish between the various bound methods
        # this is why we go around checking func_closure in the loops below!
        caller_free_vars = tuple(caller.f_locals[v] for v in caller_code.co_freevars)

        if not args:
            caller_key = (caller_code, caller_free_vars)
            if caller_key not in cls._cache:
                # type(caller_self) may not be the class that the caller is
                # actually defined in so instead we search through the MRO to
                # find the class which owns this code object we do the __dict__
                # lookup ourselves instead of with getattr to avoid grabbing an
                # attr from the parent class

                try:
                    mro_funcs = ((cls, cls.__dict__.get(caller_name))
                                 for cls in type(caller_self).__mro__)
                    caller_generator = (cls for cls, func in mro_funcs
                                        if (func and
                                            func.__code__ == caller_code and
                                            tuple(
                                                cell_contents(func.__closure__)
                                            ) == caller_free_vars)
                                        )
                    caller_class = next(caller_generator)
                except StopIteration:
                    # we also dont always know the real name that's being
                    # invoked if e.g. we are inside a decorator. so we have to
                    # do a more exhaustive search of the MRO. nicely written
                    # decorators will namke sure func.__name__ still matches
                    # afterwards but some do not
                    if cls._act_more_like_python3:
                        raise SystemError("Unable to determine implicit class")
                    else:
                        mro = type(caller_self).__mro__
                        caller_class, caller_name_in_class = (
                            find_code_in_classes(mro, caller_code, caller_free_vars)
                        )

                cls._cache[caller_key] = caller_class, caller_name_in_class
            else:
                caller_class, caller_name_in_class = cls._cache[caller_key]
        else:
            caller_class, caller_self = args

        return caller_class, caller_self, caller_name_in_class


class more_super3(super3):
    _act_more_like_python3 = False


class callable_super3(more_super3):
    def __call__(self, *args, **kwargs):
        return getattr(self, self.bound_caller_func.__name__)(*args, **kwargs)
