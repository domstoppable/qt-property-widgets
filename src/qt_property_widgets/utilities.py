import json
import typing
from enum import Enum
from pathlib import Path

from PySide6.QtGui import QColor


def property_params(**kwargs: typing.Any) -> typing.Callable:
    def decorator(prop: property) -> property:
        if prop.fget:
            prop.fget.parameters = kwargs  # type: ignore

        return prop

    return decorator


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
    def __setstate__(self, state: dict) -> None:
        properties = get_properties(self.__class__)

        for prop_name, value in state.items():
            if prop_name in properties:
                prop = properties[prop_name]

                hints = typing.get_type_hints(prop.fget)

                if "return" in hints:
                    return_type = hints["return"]
                    value = PersistentPropertiesMixin.type_convert(value, return_type)

                if prop.fset:
                    prop.fset(self, value)

    @staticmethod
    def type_convert(value: typing.Any, target_type: type) -> typing.Any:
        target_class = typing.get_origin(target_type) or target_type
        if not isinstance(value, target_class):
            if issubclass(target_class, Path):
                if value is not None:
                    value = Path(value)

            elif issubclass(target_class, Enum):
                value = target_class(value)

            elif issubclass(target_class, QColor):
                value = QColor(*value)

        elif target_class is list:
            item_type = typing.get_args(target_type)[0]
            if hasattr(item_type, "from_dict"):
                converter = item_type.from_dict
            else:
                converter = item_type

            value = [
                converter(item) if not isinstance(item, item_type) else item
                for item in value
            ]

        return value

    def to_dict(self, include_class_name: bool = False) -> dict[str, typing.Any]:
        properties = get_properties(self.__class__)
        state: dict[str, typing.Any] = {}

        if include_class_name:
            state["__class__"] = self.__class__.__name__

        for prop_name, prop in properties.items():
            if prop.fget:
                state[prop_name] = prop.fget(self)

        return state

    @classmethod
    def from_dict(
        cls: type["PersistentPropertiesMixin"], state: dict[str, typing.Any]
    ) -> "PersistentPropertiesMixin":
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
    def __init__(self, *args: typing.Any, **kwargs: typing.Any) -> None:
        kwargs["indent"] = "\t"
        super().__init__(*args, **kwargs)
        self.rel_path = None

    def default(self, obj: typing.Any) -> typing.Any:
        if isinstance(obj, Path):
            return str(obj)

        elif isinstance(obj, Enum):
            return obj.value

        elif isinstance(obj, QColor):
            return (obj.red(), obj.green(), obj.blue())

        elif isinstance(obj, PersistentPropertiesMixin):
            return obj.to_dict()

        return json.JSONEncoder.default(self, obj)
