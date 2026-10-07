"""Configuration for the pytest test suite."""

from typing import Any, Type

import pytest

from qt_property_widgets.utilities import property_params
from qt_property_widgets.widgets import PropertyWidget, WidgetSetterProperty


def _make_property(attribute_name: str, return_type: Type, **params: Any) -> property:
    """Dynamically returns a property object with a runtime-accessible type hint."""

    def getter(self: Any) -> Any:
        return getattr(self, attribute_name)

    # Manually inject the return type into the getter's annotations
    getter.__annotations__["return"] = return_type

    # Apply property_params decorator
    if params:
        params_decorator = property_params(**params)
        getter = params_decorator(getter)

    return WidgetSetterProperty(property(getter))


@pytest.fixture
def mock_property_with_params():
    def inner(attribute_name: str, return_type: Type, **params: Any) -> property:
        return _make_property(attribute_name, return_type, **params)

    return inner


@pytest.fixture
def widget_for_mock_property(qtbot):
    def inner(attribute_name: str, return_type: Type, **params: Any) -> property:
        prop = _make_property(attribute_name, return_type, **params)

        widget = PropertyWidget.from_property(prop)
        qtbot.addWidget(widget)
        widget.show()

        return widget, prop

    return inner
