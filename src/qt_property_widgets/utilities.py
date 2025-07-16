import inspect
import json
import typing as T
from enum import Enum
from pathlib import Path

from PySide6.QtCore import QObject, Signal, SignalInstance
from PySide6.QtGui import QColor, QFont


def property_params(**kwargs: T.Any) -> T.Callable:
    def decorator(getter: T.Callable) -> T.Callable:
        if hasattr(getter, "parameters"):
            params = {
                **getter.parameters,
                **kwargs
            }
        else:
            params = kwargs.copy()

        getter.parameters = params  # type: ignore

        return getter

    return decorator


def action(func: T.Optional[T.Callable] = None, **kwargs: T.Any) -> T.Any:
    class Decorator:
        def __init__(self, func: T.Callable[..., T.Any]) -> None:
            self.func: T.Callable[..., T.Any] = func
            self.owner_class: T.Optional[type[T.Any]] = None
            self.method_name: T.Optional[str] = None

        def __set_name__(self, owner: type[T.Any], name: str) -> None:
            self.owner_class = owner
            self.method_name = name

            if not hasattr(owner, "_actions"):
                owner._actions = {}

            owner._actions[self.func.__name__] = self.func

        def __get__(
            self,
            instance: T.Optional[T.Any],
            owner: T.Optional[type[T.Any]] = None
        ) -> T.Callable[..., T.Any]:
            def bound_func(*args: T.Any, **kwargs: T.Any) -> T.Any:
                return self.func(instance, *args, **kwargs)

            return bound_func

    if func is None:
        return Decorator

    return Decorator(func)


def get_class_properties(cls: type) -> dict[str, property]:
    properties = {}
    for key, value in cls.__dict__.items():
        if isinstance(value, property):
            properties[key] = value

    return properties


def get_properties(cls: type) -> dict[str, property]:
    properties = {}
    for kls in reversed(cls.mro()):
        class_props = get_class_properties(kls)
        for prop_name, prop in class_props.items():
            properties[prop_name] = prop

    return properties


class PersistentPropertiesMixin:
    def __init__(self) -> None:
        super().__init__()

        self._action_objects: dict[str, ActionObject] = {}
        if hasattr(self.__class__, "_actions"):
            for action_name, action_func in self.__class__._actions.items():
                action_object = create_action_object(action_func, self)
                self._action_objects[action_name] = action_object

                if hasattr(self, "changed") and isinstance(self.changed, SignalInstance):
                    action_object.changed.connect(self.changed.emit)

    def __setstate__(self, state: dict) -> None:
        properties = get_properties(self.__class__)

        for key, value in state.items():
            if key in properties:
                prop = properties[key]

                hints = T.get_type_hints(prop.fget)

                if "return" in hints:
                    return_type = hints["return"]
                    value = PersistentPropertiesMixin.type_convert(value, return_type)

                if prop.fset:
                    prop.fset(self, value)

            elif key in self._action_objects:
                action_object = self._action_objects[key]
                action_props = get_properties(action_object.__class__)
                for arg_name, arg_value in value.items():
                    if arg_name in action_object.args:
                        if arg_name in action_props:
                            action_prop = action_props[arg_name]
                            hints = T.get_type_hints(action_prop.fget)
                            if "return" in hints:
                                return_type = hints["return"]
                                arg_value = PersistentPropertiesMixin.type_convert(
                                    arg_value, return_type
                                )

                        action_object.args[arg_name] = arg_value

    @staticmethod
    def type_convert(value: T.Any, target_type: type) -> T.Any:
        target_class = T.get_origin(target_type) or target_type
        if not isinstance(value, target_class):
            if issubclass(target_class, Path):
                if value is not None:
                    value = Path(value)

            elif issubclass(target_class, Enum):
                value = target_class(value)

            elif issubclass(target_class, QColor):
                value = QColor(*value)

            elif issubclass(target_class, QFont):
                font = QFont(value["family"], value["pointSize"])
                font.setBold(value["bold"])
                font.setItalic(value["italic"])
                font.setUnderline(value["underline"])
                font.setStrikeOut(value["strikeOut"])

                value = font

        elif target_class is list:
            item_type = T.get_args(target_type)[0]
            if hasattr(item_type, "from_dict"):
                converter = item_type.from_dict
            else:
                converter = item_type

            value = [
                converter(item) if not isinstance(item, item_type) else item
                for item in value
            ]

        return value

    def to_dict(self, include_class_name: bool = False) -> dict[str, T.Any]:
        properties = get_properties(self.__class__)
        state: dict[str, T.Any] = {}

        if include_class_name:
            state["__class__"] = self.__class__.__name__

        for prop_name, prop in properties.items():
            if prop.fget:
                encode_ok = True
                has_params = hasattr(prop.fget, 'parameters')
                if has_params:
                    encode_ok = not prop.fget.parameters.get('dont_encode', False)

                if encode_ok:
                    state[prop_name] = prop.fget(self)

        if hasattr(self, "_action_objects"):
            for action_name, action_object in self._action_objects.items():
                state[action_name] = action_object.to_dict()

        return state

    @classmethod
    def from_dict(
        cls: type["PersistentPropertiesMixin"], state: dict[str, T.Any]
    ) -> T.Any:
        if "__class__" in state and hasattr(cls, "_known_types"):
            type_name = state["__class__"]
            for known_type in cls._known_types:
                if known_type.__name__ == type_name:
                    cls = known_type
                    break

        instance = cls()
        instance.__setstate__(state)

        return instance


class ComplexEncoder(json.JSONEncoder):
    def __init__(self, *args: T.Any, **kwargs: T.Any) -> None:
        kwargs["indent"] = "\t"
        super().__init__(*args, **kwargs)
        self.rel_path = None

    def default(self, obj: T.Any) -> T.Any:
        if isinstance(obj, Path):
            return str(obj)

        elif isinstance(obj, Enum):
            return obj.value

        elif isinstance(obj, QColor):
            return (obj.red(), obj.green(), obj.blue(), obj.alpha())

        elif isinstance(obj, PersistentPropertiesMixin):
            return obj.to_dict()

        elif isinstance(obj, QFont):
            return {
                "family": obj.family(),
                "pointSize": obj.pointSize(),
                "bold": obj.bold(),
                "italic": obj.italic(),
                "underline": obj.underline(),
                "strikeOut": obj.strikeOut(),
            }

        return json.JSONEncoder.default(self, obj)


class ActionObject(PersistentPropertiesMixin, QObject):
    changed = Signal()

    def __init__(self, func: T.Callable, instance: T.Any) -> None:
        super().__init__()

        self.func = func
        self.instance = instance
        self.args: dict[str, T.Any] = {}

        signature = inspect.signature(func)
        for param_name, param in signature.parameters.items():
            if param.default is inspect.Parameter.empty:
                self.args[param_name] = None
            else:
                self.args[param_name] = param.default

        self.args["self"] = instance

    def __call__(self) -> None:
        self.func(**self.args)


def create_action_object(func: T.Callable, instance: T.Any) -> ActionObject:
    hints = T.get_type_hints(func)

    class ActionObjectSpec(ActionObject):
        pass

    for arg_name, return_type in hints.items():
        if arg_name == "return":
            continue

        def _getter(obj: ActionObject, k: str = arg_name) -> T.Any:
            return obj.args.get(k, None)

        def _setter(obj: ActionObject, v: T.Any, k: str = arg_name) -> None:
            obj.args[k] = v

        _getter.__annotations__ = {'return': return_type}

        prop = property(_getter, _setter)
        setattr(ActionObjectSpec, arg_name, prop)

    return ActionObjectSpec(func, instance)
