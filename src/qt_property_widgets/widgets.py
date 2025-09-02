import inspect
import typing as T
from collections.abc import Mapping
from enum import Enum
from pathlib import Path

from PySide6.QtCore import (
    QSize,
    Qt,
    Signal,
    SignalInstance,
)
from PySide6.QtGui import (
    QColor,
    QColorConstants,
    QFont,
    QIcon,
    QImage,
    QPainter,
    QPainterPath,
    QPixmap,
)
from PySide6.QtWidgets import (
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFontDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSlider,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .utilities import ActionObject, create_action_object, get_properties


class WidgetSetterProperty(property):
    def __init__(self, prop: property):
        super().__init__(
            fget=prop.fget,
            fset=self.wrapped_setter,
            fdel=prop.fdel,
            doc=prop.__doc__,
        )
        self.source_prop = prop
        self.binds: dict[T.Any, list[PropertyWidget]] = {}

    def wrapped_setter(self, obj: T.Any, value: T.Any) -> None:  # noqa: C901
        def check_lists(a: list, b: list) -> bool:
            if len(a) != len(b):
                return False

            return all(a == b for a, b in zip(current_value, value, strict=True))

        if self.fget:
            current_value = self.fget(obj)
            if current_value == value:
                return

            if isinstance(value, list) and check_lists(current_value, value):
                return

        if self.source_prop.fset:
            self.source_prop.fset(obj, value)

        if hasattr(obj, "changed") and isinstance(obj.changed, SignalInstance):
            obj.changed.emit()

        for widget in self.binds.get(obj, []):
            current_widget_value = widget.value
            if current_widget_value == value:
                continue

            if isinstance(value, list) and check_lists(current_widget_value, value):
                continue

            widget.value = value

    def bind(self, obj: T.Any, widget: "PropertyWidget") -> None:
        if obj not in self.binds:
            self.binds[obj] = []

        self.binds[obj].append(widget)
        widget.destroyed.connect(lambda: self.binds[obj].remove(widget))
        if self.fset:
            widget.value_changed.connect(lambda v: self.wrapped_setter(obj, v))


class PropertyWidget(QWidget):
    deferred_type_widgets: T.ClassVar[list[type]] = []
    _known_type_widgets: T.ClassVar[dict[type, type]] = {}
    value_changed = Signal(object)

    def __init__(self) -> None:
        super().__init__()

        self.grid_layout = QGridLayout(self)
        self.grid_layout.setContentsMargins(0, 0, 0, 0)

        self._prop_setter = None

    def __init_subclass__(cls: type, **kwargs: T.Any) -> None:
        super().__init_subclass__(**kwargs)  # type: ignore

        PropertyWidget.deferred_type_widgets.append(cls)

    @property
    def value(self) -> T.Any:
        raise NotImplementedError("Subclasses must override the 'value' property.")

    @value.setter
    def value(self, value: T.Any) -> None:
        raise NotImplementedError(
            "Subclasses must override the 'value' property setter."
        )

    @staticmethod
    def from_property(
        prop: property | str, instance: T.Any = None
    ) -> T.Optional["PropertyWidget"]:
        if isinstance(prop, str):
            actual_prop = getattr(instance.__class__, prop)
        else:
            actual_prop = prop

        widget_class = None

        if hasattr(actual_prop.fget, "parameters"):
            params = actual_prop.fget.parameters
            if "widget" in params:
                widget_class = actual_prop.fget.parameters["widget"]
                if widget_class is None:
                    return None

        if widget_class is None:
            hints = T.get_type_hints(actual_prop.fget)
            value_type = hints.get("return", str)
            widget_class = PropertyWidget.get_widget_class_from_value_class(value_type)

        w: PropertyWidget = widget_class.from_property_impl(actual_prop)
        if instance is not None:
            w.value = actual_prop.fget(instance)
            if not isinstance(actual_prop, WidgetSetterProperty):
                existing_props = get_properties(instance.__class__)
                for k, v in existing_props.items():
                    if v == actual_prop:
                        actual_prop = WidgetSetterProperty(actual_prop)
                        setattr(instance.__class__, k, actual_prop)
                        break
                else:
                    print("Could not find prop to replace with WidgetSetterProperty")

            actual_prop.bind(instance, w)

        return w

    @staticmethod
    def from_type(cls: type) -> T.Union["PropertyWidget", None]:
        widget_class = PropertyWidget.get_widget_class_from_value_class(cls)
        return widget_class.from_type(cls)

    @staticmethod
    def get_widget_class_from_value_class(cls: type) -> type["PropertyWidget"]:
        candidates = []
        for kls, widget_cls in PropertyWidget.get_known_type_widgets().items():
            if is_subtype(cls, kls):
                candidates.append(widget_cls)

        if not candidates:
            raise ValueError(f"No widget class found for type {cls}")

        # Sort candidates by specificity (most specific class comes first)
        candidates.sort(key=lambda c: len(c.mro()) + (999 if c == PropertyForm else 0))
        return candidates[0]

    @staticmethod
    def from_property_impl(prop: property) -> "PropertyWidget":
        raise NotImplementedError("Subclasses must implement 'from_property_impl'.")

    @staticmethod
    def get_known_type_widgets() -> dict[type, type]:
        for cls in PropertyWidget.deferred_type_widgets:
            if hasattr(cls, "value") and cls.value.fget:
                hints = T.get_type_hints(cls.value.fget)
                if "return" in hints:
                    PropertyWidget._known_type_widgets[hints["return"]] = cls

        PropertyWidget.deferred_type_widgets.clear()

        return PropertyWidget._known_type_widgets

class PathWidget(PropertyWidget):
    value_changed = Signal(Path)

    @staticmethod
    def from_property_impl(prop: property) -> "PathWidget":
        widget = PathWidget()

        if prop.fget and hasattr(prop.fget, "parameters"):
            parameters = prop.fget.parameters
            if "directory_mode" in parameters:
                widget.directory_mode = parameters["directory_mode"]

        widget.directory_mode = True

        return widget

    def __init__(self) -> None:
        super().__init__()

        self.widget = QPushButton()
        self.widget.clicked.connect(lambda _: self._on_browse_clicked())
        self._value: Path = Path(".")

        self.grid_layout.addWidget(self.widget, 0, 0)

        self.filter = ""
        self.directory_mode = False

    def _on_browse_clicked(self) -> None:
        if self.directory_mode:
            value = QFileDialog.getExistingDirectory(
                self, "Open Folder", str(self._value)
            )
        else:
            value = QFileDialog.getOpenFileName(
                self, "Open File", str(self._value), self.filter
            )[0]

        if value == "":
            return

        self.value = Path(value)
        self._emit_value_changed()

    def _emit_value_changed(self) -> None:
        self.value_changed.emit(self._value)

    def _update_text(self):
        if self._value is None:
            self.widget.setText("🖿")
        else:
            as_string = str(self._value.resolve().stem)
            if len(as_string) > 32:
                as_string = as_string[:14] + "..." + as_string[-14:]

            self.widget.setText(f"🖿 {as_string}")

    @property
    def value(self) -> Path:
        return self._value

    @value.setter
    def value(self, value: str | Path) -> None:
        self._value = Path(value or ".")
        self._update_text()


class EnumComboWidget(PropertyWidget):
    value_changed = Signal(Enum)

    @staticmethod
    def from_property_impl(prop: property) -> "EnumComboWidget":
        hints = T.get_type_hints(prop.fget)
        enum_class = hints["return"]
        return EnumComboWidget(enum_class)

    def __init__(self, enum_class: type[Enum]) -> None:
        super().__init__()

        self.widget = QComboBox()
        for e in enum_class:
            self.widget.addItem(e.name, e)

        self.widget.currentIndexChanged.connect(
            lambda: self.value_changed.emit(self.value)
        )

        self.grid_layout.addWidget(self.widget, 0, 0)

    @property
    def value(self) -> Enum:
        data: Enum = self.widget.currentData()
        return data

    @value.setter
    def value(self, value: Enum) -> None:
        self.widget.setCurrentIndex(self.widget.findData(value))


class FontWidget(PropertyWidget):
    value_changed = Signal(QFont)

    @staticmethod
    def from_property_impl(prop: property) -> "FontWidget":
        return FontWidget()

    def __init__(self) -> None:
        super().__init__()

        self._font = QFont()
        self.widget = QPushButton()
        self.widget.clicked.connect(lambda: self._on_clicked())

        self.grid_layout.addWidget(self.widget, 0, 0)
        self._update_text()

    def _on_clicked(self) -> None:
        ok, font = QFontDialog.getFont(self._font, self)
        if ok:
            self.value = font
            self.value_changed.emit(self.value)

    def _update_text(self):
        self.widget.setText(f"{self._font.family()} {self._font.pointSize()}")
        self.widget.setFont(self._font)

    @property
    def value(self) -> QFont:
        return self._font

    @value.setter
    def value(self, value: QFont) -> None:
        self._font = value
        self._update_text()


class ColorWidget(PropertyWidget):
    value_changed = Signal(QColor)

    @staticmethod
    def from_property_impl(prop: property) -> "ColorWidget":
        return ColorWidget()

    def __init__(self) -> None:
        super().__init__()

        self.spacer = QWidget()
        self.spacer.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.button = QToolButton()
        self.button.setStyleSheet("border: none;")
        self.button.setIconSize(QSize(20, 20))
        self.grid_layout.addWidget(self.spacer, 0, 0)
        self.grid_layout.addWidget(self.button, 0, 1)

        self._color: QColor = QColor(255, 255, 255)

        self.button.clicked.connect(self._on_clicked)

        self._setup_button()

    def _on_clicked(self) -> None:
        show_alpha = QColorDialog.ColorDialogOption.ShowAlphaChannel
        color = QColorDialog.getColor(self._color, self, options=show_alpha)
        if color.isValid():
            self.value = color

    def _setup_button(self) -> None:
        if self._color is None:
            return

        self.button.setText(self._color.name())

        icon_size = 64
        self.icon_canvas_image = QImage(
            icon_size, icon_size, QImage.Format.Format_ARGB32
        )
        painter = QPainter(self.icon_canvas_image)
        path = QPainterPath()
        path.addEllipse(0, 0, icon_size, icon_size)
        painter.setClipPath(path)
        for y in range(0, icon_size, 16):
            for x in range(0, icon_size, 16):
                if (x // 16 + y // 16) % 2 == 0:
                    painter.fillRect(x, y, 16, 16, QColorConstants.LightGray)
                else:
                    painter.fillRect(x, y, 16, 16, QColorConstants.DarkGray)

        painter.setBrush(self._color)
        painter.drawEllipse(0, 0, icon_size, icon_size)
        painter.end()

        self.button.setIcon(QIcon(QPixmap.fromImage(self.icon_canvas_image)))

    @property
    def value(self) -> QColor:
        return self._color

    @value.setter
    def value(self, value: QColor) -> None:
        self._color = value
        self._setup_button()
        self.value_changed.emit(self._color)


class MultiLineTextWidget(PropertyWidget):
    value_changed = Signal(str)

    @staticmethod
    def from_property_impl(prop: property) -> "MultiLineTextWidget":
        return MultiLineTextWidget()

    def __init__(self) -> None:
        super().__init__()

        self.widget = QPlainTextEdit()
        self.widget.textChanged.connect(lambda: self.value_changed.emit(self.value))
        self.grid_layout.addWidget(self.widget, 0, 0)

    @property
    def value(self) -> str:
        return self.widget.toPlainText()

    @value.setter
    def value(self, value: str) -> None:
        self.widget.setPlainText(value)


class TextWidget(PropertyWidget):
    value_changed = Signal(str)

    @staticmethod
    def from_property_impl(prop: property) -> "TextWidget":
        return TextWidget()

    @staticmethod
    def from_type(cls: type) -> "TextWidget":
        return TextWidget()

    def __init__(self) -> None:
        super().__init__()

        self.widget = QLineEdit()
        self.widget.textChanged.connect(lambda: self.value_changed.emit(self.value))

        self.grid_layout.addWidget(self.widget, 0, 0)

    @property
    def value(self) -> str:
        return self.widget.text()

    @value.setter
    def value(self, value: str) -> None:
        self.widget.setText(value)


class SpinboxWidget(PropertyWidget):
    value_changed = Signal(float)

    @staticmethod
    def from_type(cls: type) -> "SpinboxWidget":
        return SpinboxWidget()

    @classmethod
    def from_property_impl(cls: type, prop: property) -> "SpinboxWidget":
        widget: SpinboxWidget = cls()

        if prop.fget and hasattr(prop.fget, "parameters"):
            parameters = prop.fget.parameters
            if "min" in parameters:
                widget.min = parameters["min"]

            if "max" in parameters:
                widget.max = parameters["max"]

            if "step" in parameters:
                widget.step = parameters["step"]

            if "decimals" in parameters:
                widget.decimals = parameters["decimals"]

            has_range = "max" in parameters and "min" in parameters
            widget.slider.setVisible(parameters.get("show_slider", has_range))

            widget.spinbox.setVisible(parameters.get("show_spinbox", True))

        return widget

    def __init__(self) -> None:
        super().__init__()

        self.slider = QSlider(self)
        self.slider.setOrientation(Qt.Orientation.Horizontal)
        self.slider.valueChanged.connect(lambda: self.spinbox.setValue(self.slider.value() / 10**self.decimals))
        self.slider.setVisible(False)
        self.grid_layout.addWidget(self.slider, 0, 0)

        self.spinbox = QDoubleSpinBox(self)
        self.spinbox.valueChanged.connect(lambda: self.value_changed.emit(self.value))
        self.spinbox.valueChanged.connect(lambda: self.slider.setValue(int(self.spinbox.value() * 10**self.decimals)))
        self.grid_layout.addWidget(self.spinbox, 0, 1)

    @property
    def min(self) -> float:
        return self.spinbox.minimum()

    @min.setter
    def min(self, value: float) -> None:
        self.spinbox.setMinimum(value)
        self.slider.setMinimum(value * 10**self.decimals)

    @property
    def max(self) -> float:
        return self.spinbox.maximum()

    @max.setter
    def max(self, value: float) -> None:
        self.spinbox.setMaximum(value)
        self.slider.setMaximum(value * 10**self.decimals)

    @property
    def step(self) -> float:
        return self.spinbox.singleStep()

    @step.setter
    def step(self, value: float) -> None:
        self.spinbox.setSingleStep(value)
        self.slider.setSingleStep(value * 10**self.decimals)

    @property
    def decimals(self) -> int:
        return self.spinbox.decimals()

    @decimals.setter
    def decimals(self, value: int) -> None:
        self.spinbox.setDecimals(value)

        self.slider.setMaximum(self.max * 10**value)
        self.slider.setMinimum(self.min * 10**value)
        self.slider.setSingleStep(self.step * 10**value)

    @property
    def value(self) -> float:
        return self.spinbox.value()

    @value.setter
    def value(self, value: float) -> None:
        self.spinbox.setValue(value)


class IntSpinboxWidget(SpinboxWidget):
    value_changed = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self.spinbox.setDecimals(0)

    @property  # type: ignore
    def value(self) -> int:
        return int(self.spinbox.value())

    @value.setter
    def value(self, value: int) -> None:
        self.spinbox.setValue(value)


class BoolWidget(PropertyWidget):
    value_changed = Signal(bool)

    @staticmethod
    def from_property_impl(prop: property) -> "BoolWidget":
        return BoolWidget()

    def __init__(self) -> None:
        super().__init__()

        self.checkbox = QToolButton()
        self.checkbox.setCheckable(True)
        self.checkbox.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.checkbox.clicked.connect(self.on_clicked)
        self.checkbox.setStyleSheet("""
            font-family: monospace;
            padding: -1 -2 0 -2;
        """)

        self.spacer = QWidget()
        self.spacer.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )

        self.grid_layout.addWidget(self.spacer, 0, 0)
        self.grid_layout.addWidget(self.checkbox, 0, 1)

    def on_clicked(self):
        self.value_changed.emit(self.value)
        self.update_indicator()

    def update_indicator(self):
        self.checkbox.setText("✔" if self.value else " ")

    @property
    def value(self) -> bool:
        return self.checkbox.isChecked()

    @value.setter
    def value(self, value: bool) -> None:
        self.checkbox.setChecked(value)
        self.update_indicator()
        self.value_changed.emit(value)


class FlagsWidget(PropertyWidget):
    value_changed = Signal(object)

    @staticmethod
    def from_property_impl(prop: property) -> "FlagsWidget":
        return FlagsWidget()

    def __init__(self) -> None:
        super().__init__()
        self._flags = {}
        self.grid_layout.setContentsMargins(5, 3, 0, 0)

    @property
    def value(self) -> T.Mapping[str, bool]:
        return self._flags

    @value.setter
    def value(self, value: T.Mapping[str, bool]) -> None:
        self._flags = value

        # remove widgets
        while self.grid_layout.count() > 0:
            self.grid_layout.takeAt(0).widget().setParent(None)

        sorted_keys = sorted(self._flags.keys())

        for idx, k in enumerate(sorted_keys):
            w = BoolWidget()
            w.value = self._flags[k]
            w.value_changed.connect(lambda new_v, k=k: self._on_value_changed(k, new_v))
            self.grid_layout.addWidget(QLabel(k), idx, 0)
            self.grid_layout.addWidget(w, idx, 1)

        self.value_changed.emit(value)


    def _on_value_changed(self, key: str, value: bool) -> None:
        tmp_flags = self._flags.copy()
        tmp_flags[key] = value
        self.value = tmp_flags


class ValueListItemWidget(QWidget):
    def __init__(self, item_widget: PropertyWidget | None) -> None:
        super().__init__()

        self.item_widget = item_widget
        self.delete_button = QPushButton("×", self)  # noqa: RUF001
        self.delete_button.setFixedSize(20, 20)

        if isinstance(item_widget, PropertyForm):
            layout = QVBoxLayout(self)
            title_bar = QWidget()
            title_bar.setStyleSheet("font-weight: bold")

            tbar_layout = QHBoxLayout()
            tbar_layout.setContentsMargins(0, 0, 0, 0)
            tbar_layout.addWidget(QLabel(item_widget.value.__class__.__name__))
            tbar_layout.addWidget(self.delete_button)
            title_bar.setLayout(tbar_layout)

            layout.addWidget(title_bar)
            layout.addWidget(item_widget)
        else:
            layout = QHBoxLayout(self)
            if item_widget is not None:
                layout.addWidget(item_widget, stretch=1)

            layout.addWidget(self.delete_button)

        layout.setContentsMargins(0, 0, 0, 0)


class ValueListWidget(PropertyWidget):
    value_changed = Signal(list)

    def __init__(self, item_class: type, prop_parameters: dict | None = None) -> None:
        if prop_parameters is None:
            prop_parameters = {}

        super().__init__()

        self.item_class = item_class
        self.prop_parameters = prop_parameters

        self.container_widget = QWidget(self)
        self.container_layout = QVBoxLayout(self.container_widget)
        self.container_layout.setContentsMargins(0, 0, 0, 0)

        # Button for adding a new item.
        add_button = QPushButton(self.prop_parameters.get("add_button_text", "Add value"), self)
        add_button.clicked.connect(self.on_add_button_clicked)

        self.grid_layout.addWidget(self.container_widget, 0, 0)
        self.grid_layout.addWidget(add_button, 1, 0)

        self.item_widgets: list[ValueListItemWidget] = []

    def on_add_button_clicked(self) -> None:
        if self.prop_parameters.get("use_subclass_selector", False) and hasattr(
            self.item_class, "_known_types"
        ):
            dialog = QDialog(self)
            dialog.setWindowTitle("Select Type")

            layout = QVBoxLayout()
            dialog.setLayout(layout)

            combo_box = QComboBox(dialog)
            for subtype in self.item_class._known_types:
                combo_box.addItem(subtype.__name__, subtype)
            layout.addWidget(combo_box)

            button_box = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Ok
                | QDialogButtonBox.StandardButton.Cancel,
                dialog,
            )
            layout.addWidget(button_box)

            button_box.accepted.connect(dialog.accept)
            button_box.rejected.connect(dialog.reject)

            if dialog.exec() == QDialog.DialogCode.Accepted:
                selected_class = combo_box.currentData()
                v = selected_class()
            else:
                return
        else:
            v = self.item_class()

        self.add_item(v)
        self.value_changed.emit(self.value)

    def add_item(self, obj: T.Any) -> None:
        item_widget = PropertyWidget.from_type(self.item_class)
        item_widget.value_changed.connect(lambda _: self.value_changed.emit(self.value))

        if item_widget and hasattr(item_widget, "value"):
            item_widget.value = obj

        list_item_wrapper: ValueListItemWidget = ValueListItemWidget(item_widget)
        list_item_wrapper.delete_button.clicked.connect(
            lambda: self.remove_item(list_item_wrapper)
        )

        self.container_layout.addWidget(list_item_wrapper)

    def remove_item(self, item_widget: ValueListItemWidget) -> None:
        self.container_layout.removeWidget(item_widget)
        item_widget.deleteLater()
        self.value_changed.emit(self.value)

    @staticmethod
    def from_property_impl(prop: property) -> "ValueListWidget":
        hints = T.get_type_hints(prop.fget)
        return_type = hints["return"]
        item_type = T.get_args(return_type)[0]

        prop_parameters = None
        if prop.fget and hasattr(prop.fget, "parameters"):
            prop_parameters = prop.fget.parameters

        return ValueListWidget(item_type, prop_parameters)

    @staticmethod
    def from_type(cls: type) -> "ValueListWidget":
        return ValueListWidget(cls)

    @property
    def value(self) -> list:
        values = []
        for i in range(self.container_layout.count()):
            widget = self.container_layout.itemAt(i).widget()
            if hasattr(widget, "item_widget"):
                item_widget = widget.item_widget

            values.append(item_widget.value)

        return values

    @value.setter
    def value(self, value: list) -> None:
        while self.container_layout.count():
            item = self.container_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        for v in value:
            self.add_item(v)


class PropertyForm(PropertyWidget):
    value_changed = Signal(object)
    property_changed = Signal(str, object)

    @staticmethod
    def from_property_impl(prop: property) -> "PropertyForm":
        hints = T.get_type_hints(prop.fget)
        return PropertyForm.from_type(hints["return"])

    @staticmethod
    def from_type(cls: type) -> "PropertyForm":
        return PropertyForm(cls())

    def __init__(self, obj: object | None) -> None:
        super().__init__()

        self._setup_grid()
        self.value = obj

    def _setup_grid(self) -> None:
        self.form_layout = QFormLayout()
        self.form_layout.setVerticalSpacing(4)

        self.actions_container = QVBoxLayout()

        gl = self.grid_layout
        gl.addLayout(self.form_layout, gl.rowCount(), 0)
        gl.addLayout(self.actions_container, gl.rowCount(), 0)

    @property
    def value(self) -> object:
        return self._value

    @value.setter
    def value(self, value: object) -> None:
        self._value = value
        self.value_changed.emit(value)

        while self.form_layout.count():
            self.form_layout.removeRow(0)

        self._setup_form()

    def _setup_form(self) -> None:
        props = get_properties(self.value.__class__)
        for property_name, prop in props.items():
            prop_widget = PropertyWidget.from_property(prop, self.value)

            if prop_widget is not None:
                label = property_name.replace("_", " ").capitalize()
                self.form_layout.addRow(label, prop_widget)
                prop_widget.value_changed.connect(
                    lambda v, n=property_name: self.property_changed.emit(n, v)
                )

        while self.actions_container.count():
            item = self.actions_container.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        if hasattr(self.value, "_action_objects"):
            for action_name, action_object in self.value._action_objects.items():
                self.add_action(action_name, action_object)

            self.actions_container.addStretch(1)

    def add_action(self, action_name: str, action_object: object | T.Callable) -> None:
        if not isinstance(action_object, ActionObject):
            action_object = create_action_object(action_object, self.value)

        action_prop_form = PropertyWidget.from_type(action_object.__class__)
        action_prop_form.value = action_object
        self.actions_container.addWidget(action_prop_form)

    @property
    def has_widgets(self) -> bool:
        return len(self.findChildren(QWidget)) > 0


def is_subtype(child_type, parent_type) -> bool:
    # Exact match
    if child_type == parent_type:
        return True

    # Plain‐class check (int, str, custom classes without subscripting)
    if inspect.isclass(child_type) and inspect.isclass(parent_type):
        try:
            if issubclass(child_type, parent_type):
                return True
        except TypeError:
            pass

    # Peel off origins & args for parameterized generics
    c_origin = T.get_origin(child_type)
    p_origin = T.get_origin(parent_type)
    c_args   = T.get_args(child_type)
    p_args   = T.get_args(parent_type)

    # If both are parameterized and same arity
    if c_origin and p_origin and len(c_args) == len(p_args):
        # Standard: same origin (or subclass) + covariant args
        same_origin = (
            c_origin == p_origin
            or (inspect.isclass(c_origin)
               and inspect.isclass(p_origin)
               and issubclass(c_origin, p_origin))
        )
        if same_origin and all(is_subtype(ca, pa) for ca, pa in zip(c_args, p_args)):
            return True

        # SPECIAL RULE: any Mapping[K,V] → any other Mapping[K,V]
        if (
            inspect.isclass(c_origin)
            and issubclass(c_origin, Mapping)
            and inspect.isclass(p_origin)
            and issubclass(p_origin, Mapping)
            and all(is_subtype(ca, pa) for ca, pa in zip(c_args, p_args))
        ):
            return True

    # Raw‐generic parent: allow GenericAlias → its origin
    #    e.g. child_type = list[X], parent_type = list
    if c_origin and inspect.isclass(parent_type):
        if c_origin == parent_type or (
            inspect.isclass(c_origin) and issubclass(c_origin, parent_type)
        ):
            return True

    return False


class ActionForm(PropertyForm):
    @staticmethod
    def from_property_impl(prop: property) -> "ActionForm":
        hints = T.get_type_hints(prop.fget)
        return ActionForm.from_type(hints["return"])

    @staticmethod
    def from_type(cls: type) -> "ActionForm":
        return ActionForm(cls(lambda: None, None))

    def __init__(self, obj: object | None) -> None:
        self.title_label = QLabel()

        super().__init__(obj)

    def _setup_grid(self) -> None:
        self.grid_layout.addWidget(self.title_label, 0, 0)
        super()._setup_grid()

    def _setup_form(self) -> None:
        super()._setup_form()
        self.action_button = QPushButton()
        self.action_button.clicked.connect(self._on_action_button_pressed)
        self.form_layout.addRow("", self.action_button)

    def _on_action_button_pressed(self) -> T.Any:
        return self.value()

    @property
    def value(self) -> ActionObject:
        return PropertyForm.value.fget(self)

    @value.setter
    def value(self, value: ActionObject) -> None:
        PropertyForm.value.fset(self, value)
        friendly_name = value.func.__name__.replace("_", " ").title()
        self.title_label.setText(f"<b>{friendly_name}</b>")
        self.action_button.setText(f"Run: {friendly_name}")
