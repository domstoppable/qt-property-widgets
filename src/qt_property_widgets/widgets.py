import typing as T
from enum import Enum
from pathlib import Path

from PySide6.QtCore import (
    Qt,
    Signal,
    SignalInstance,
)
from PySide6.QtGui import (
    QColor,
    QColorConstants,
    QFont,
    QFontDatabase,
    QIcon,
    QImage,
    QPainter,
    QPixmap,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .utilities import get_properties


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
                return

            widget.value = value

    def bind(self, obj: T.Any, widget: "PropertyWidget") -> None:
        if obj not in self.binds:
            self.binds[obj] = []

        self.binds[obj].append(widget)
        if self.fset:
            widget.value_changed.connect(lambda v: self.fset(obj, v))


class PropertyWidget(QWidget):
    known_type_widgets: T.ClassVar[dict[type, type]] = {}
    value_changed = Signal(object)

    def __init__(self) -> None:
        super().__init__()

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

        self._prop_setter = None

    def __init_subclass__(cls: type, **kwargs: T.Any) -> None:
        super().__init_subclass__(**kwargs)  # type: ignore

        if hasattr(cls, "value") and cls.value.fget:
            hints = T.get_type_hints(cls.value.fget)
            if "return" in hints:
                PropertyWidget.known_type_widgets[hints["return"]] = cls

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
    ) -> T.Union["PropertyWidget", None]:
        if isinstance(prop, str):
            actual_prop = getattr(instance.__class__, prop)
        else:
            actual_prop = prop

        if (
            hasattr(actual_prop.fget, "parameters")
            and "widget" in actual_prop.fget.parameters
        ):
            widget_class = actual_prop.fget.parameters["widget"]
            if widget_class is None:
                return None

        else:
            hints = T.get_type_hints(actual_prop.fget)
            value_type = hints.get("return", str)
            widget_class = PropertyWidget.get_widget_class_from_value_class(value_type)

        w: PropertyWidget = widget_class.from_property_impl(actual_prop)
        if instance is not None:
            w.value = actual_prop.fget(instance)
            if not isinstance(actual_prop, WidgetSetterProperty):
                actual_prop = WidgetSetterProperty(actual_prop)
                setattr(instance.__class__, actual_prop.fget.__name__, actual_prop)

            actual_prop.bind(instance, w)

        return w

    @staticmethod
    def from_type(cls: type) -> T.Union["PropertyWidget", None]:
        widget_class = PropertyWidget.get_widget_class_from_value_class(cls)
        return widget_class.from_type(cls)

    @staticmethod
    def get_widget_class_from_value_class(cls: type) -> type["PropertyWidget"]:
        value_class = T.get_origin(cls) or cls
        candidates = []
        for kls, widget_cls in PropertyWidget.known_type_widgets.items():
            if issubclass(value_class, kls):
                candidates.append(widget_cls)

        if not candidates:
            raise ValueError(f"No widget class found for type {cls}")

        # Sort candidates by specificity (most specific class comes first)
        candidates.sort(key=lambda c: len(c.mro()) + (999 if c == PropertyForm else 0))
        return candidates[0]

    @staticmethod
    def from_property_impl(prop: property) -> "PropertyWidget":
        raise NotImplementedError("Subclasses must implement 'from_property_impl'.")


class PathWidget(PropertyWidget):
    value_changed = Signal(Path)

    @staticmethod
    def from_property_impl(prop: property) -> "PathWidget":
        widget = PathWidget()
        return widget

    def __init__(self) -> None:
        super().__init__()

        self.widget = QLineEdit()
        self.browse_button = QToolButton()
        self.browse_button.setText("🖿")
        self.browse_button.clicked.connect(lambda _: self._on_browse_clicked())

        layout = self.layout()
        if layout:
            layout.addWidget(self.widget)
            layout.addWidget(self.browse_button)

        self.widget.editingFinished.connect(self._emit_value_changed)
        self.filter = ""
        self.directory_mode = False

    def _on_browse_clicked(self) -> None:
        if self.directory_mode:
            value = QFileDialog.getExistingDirectory(
                self, "Open Folder", self.widget.text()
            )
        else:
            value = QFileDialog.getOpenFileName(
                self, "Open File", self.widget.text(), self.filter
            )[0]

        if value == "":
            return

        self.widget.setText(value)
        self._emit_value_changed()

    def _emit_value_changed(self) -> None:
        path_str = self.widget.text()
        if path_str == "":
            self.value_changed.emit(None)
        else:
            self.value_changed.emit(Path(path_str))

    @property
    def value(self) -> Path:
        return Path(self.widget.text())

    @value.setter
    def value(self, value: str | Path) -> None:
        if value is None:
            self.widget.setText("")
        else:
            self.widget.setText(str(value))


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

        layout = self.layout()
        if layout:
            layout.addWidget(self.widget)

    @property
    def value(self) -> Enum:
        data: Enum = self.widget.currentData()
        return data

    @value.setter
    def value(self, value: Enum) -> None:
        self.widget.setCurrentIndex(self.widget.findData(value))


class FontComboWidget(PropertyWidget):
    value_changed = Signal(QFont)

    @staticmethod
    def from_property_impl(prop: property) -> "FontComboWidget":
        return FontComboWidget()

    def __init__(self) -> None:
        super().__init__()

        self.widget = QComboBox()

        for family in QFontDatabase.families():
            self.widget.addItem(family, family)

        self.widget.currentIndexChanged.connect(
            lambda: self.value_changed.emit(self.value)
        )

        layout = self.layout()
        if layout:
            layout.addWidget(self.widget)

    @property
    def value(self) -> QFont:
        font: QFont = self.widget.currentData()
        return font

    @value.setter
    def value(self, value: QFont) -> None:
        idx = self.widget.findData(value)
        if idx == -1:
            self.widget.addItem(f"{value} [NOT FOUND]", value)
            idx = self.widget.count() - 1

        self.widget.setCurrentIndex(idx)


class ColorWidget(PropertyWidget):
    value_changed = Signal(QColor)

    @staticmethod
    def from_property_impl(prop: property) -> "ColorWidget":
        return ColorWidget()

    def __init__(self) -> None:
        super().__init__()

        self.button = QPushButton()
        layout = self.layout()
        if layout:
            layout.addWidget(self.button)

        self._color: QColor = QColor(255, 255, 255)

        self.button.clicked.connect(self._on_clicked)
        self.setStyleSheet("QPushButton { font-family: monospace; }")

        icon_size = 64
        self.icon_canvas_image = QImage(
            icon_size, icon_size, QImage.Format.Format_ARGB32
        )
        painter = QPainter(self.icon_canvas_image)
        painter.setPen(Qt.PenStyle.NoPen)
        for y in range(0, icon_size, 16):
            for x in range(0, icon_size, 16):
                if (x // 16 + y // 16) % 2 == 0:
                    painter.fillRect(x, y, 16, 16, QColorConstants.LightGray)
                else:
                    painter.fillRect(x, y, 16, 16, QColorConstants.DarkGray)

        self._setup_button()

    def _on_clicked(self) -> None:
        show_alpha = QColorDialog.ColorDialogOption.ShowAlphaChannel
        color = QColorDialog.getColor(self._color, self, options=show_alpha)
        if color.isValid():
            self.value = color

    def _setup_button(self) -> None:
        self.button.setText(self._color.name())

        image = QImage(self.icon_canvas_image)
        painter = QPainter(image)
        painter.fillRect(0, 0, image.width(), image.height(), self._color)
        painter.end()

        self.button.setIcon(QIcon(QPixmap.fromImage(image)))

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
        layout = self.layout()
        if layout:
            layout.addWidget(self.widget)

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

        layout = self.layout()
        if layout:
            layout.addWidget(self.widget)

    @property
    def value(self) -> str:
        return self.widget.text()

    @value.setter
    def value(self, value: str) -> None:
        self.widget.setText(value)


class SpinboxWidget(PropertyWidget):
    value_changed = Signal(float)

    @classmethod
    def from_property_impl(cls: type, prop: property) -> "SpinboxWidget":
        widget: SpinboxWidget = cls()

        if prop.fget and hasattr(prop.fget, "parameters"):
            parameters = prop.fget.parameters
            if "min" in parameters:
                widget.spinbox.setMinimum(parameters["min"])

            if "max" in parameters:
                widget.spinbox.setMaximum(parameters["max"])

            if "step" in parameters:
                widget.spinbox.setSingleStep(parameters["step"])

            if "decimals" in parameters:
                widget.spinbox.setDecimals(parameters["decimals"])

        return widget

    def __init__(self) -> None:
        super().__init__()

        self.spinbox = QDoubleSpinBox()
        self.spinbox.valueChanged.connect(lambda: self.value_changed.emit(self.value))

        layout = self.layout()
        if layout:
            layout.addWidget(self.spinbox)

    @property
    def min(self) -> float:
        return self.spinbox.minimum()

    @min.setter
    def min(self, value: float) -> None:
        self.spinbox.setMinimum(value)

    @property
    def max(self) -> float:
        return self.spinbox.maximum()

    @max.setter
    def max(self, value: float) -> None:
        self.spinbox.setMaximum(value)

    @property
    def step(self) -> float:
        return self.spinbox.singleStep()

    @step.setter
    def step(self, value: float) -> None:
        self.spinbox.setSingleStep(value)

    @property
    def decimals(self) -> int:
        return self.spinbox.decimals()

    @decimals.setter
    def decimals(self, value: int) -> None:
        self.spinbox.setDecimals(value)

    @property
    def value(self) -> float:
        return self.spinbox.value()

    @value.setter
    def value(self, value: float) -> None:
        self.spinbox.setValue(value)


class IntSpinboxWidget(SpinboxWidget):
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

        self.checkbox = QCheckBox()
        self.checkbox.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.checkbox.stateChanged.connect(
            lambda _: self.value_changed.emit(self.value)
        )

        layout = self.layout()
        if layout:
            layout.addWidget(self.checkbox)

    @property
    def value(self) -> bool:
        return self.checkbox.isChecked()

    @value.setter
    def value(self, value: bool) -> None:
        self.checkbox.setChecked(value)
        self.value_changed.emit(value)


class ValueListItemWidget(QWidget):
    def __init__(self, item_widget: PropertyWidget | None) -> None:
        super().__init__()

        self.item_widget = item_widget
        self.delete_button = QPushButton("×", self)  # noqa: RUF001
        self.delete_button.setFixedSize(20, 20)

        if isinstance(item_widget, PropertyForm):
            self.setLayout(QVBoxLayout())
            title_bar = QWidget()
            title_bar.setStyleSheet("font-weight: bold")

            tbar_layout = QHBoxLayout()
            tbar_layout.setContentsMargins(0, 0, 0, 0)
            tbar_layout.addWidget(QLabel(item_widget.value.__class__.__name__))
            tbar_layout.addWidget(self.delete_button)
            title_bar.setLayout(tbar_layout)

            layout = self.layout()
            if layout:
                layout.addWidget(title_bar)
                layout.addWidget(item_widget)
        else:
            layout = QHBoxLayout()
            if item_widget is not None:
                layout.addWidget(item_widget, stretch=1)

            layout.addWidget(self.delete_button)
            self.setLayout(layout)


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
        self.container_layout.setSpacing(5)

        # Button for adding a new item.
        add_button = QPushButton("Add value", self)
        add_button.clicked.connect(self.on_add_button_clicked)

        layout = self.layout()
        if layout:
            layout.addWidget(self.container_widget)
            layout.addWidget(add_button)

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

    def __init__(self, obj: object) -> None:
        super().__init__()

        self.form_layout = QFormLayout()
        self.form_layout.setSpacing(0)

        layout = self.layout()
        if layout and hasattr(layout, "addLayout"):
            layout.addLayout(self.form_layout)

        self.value = obj

    @property
    def value(self) -> object:
        return self._value

    @value.setter
    def value(self, value: object) -> None:
        self._value = value
        self.value_changed.emit(value)

        while self.form_layout.count():
            item = self.form_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        props = get_properties(value.__class__)
        for property_name, prop in props.items():
            prop_widget = PropertyWidget.from_property(prop, value)

            if prop_widget is not None:
                label = property_name.replace("_", " ").capitalize()
                self.form_layout.addRow(label, prop_widget)
                prop_widget.value_changed.connect(
                    lambda v, n=property_name: self.property_changed.emit(n, v)
                )
