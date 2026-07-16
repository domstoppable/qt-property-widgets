import math

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QColorConstants, QPainter
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSlider,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)


class ChannelSlider(QWidget):
    valueChanged = Signal(int)

    def __init__(
        self,
        label: str,
        minimum: int = 0,
        maximum: int = 255,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._updating = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._label = QLabel(label)
        self._label.setFixedWidth(16)
        layout.addWidget(self._label)

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(minimum, maximum)
        layout.addWidget(self._slider, 1)

        self._spinbox = QSpinBox()
        self._spinbox.setRange(minimum, maximum)
        self._spinbox.setFixedWidth(60)
        layout.addWidget(self._spinbox)

        self._slider.valueChanged.connect(self._on_slider_changed)
        self._spinbox.valueChanged.connect(self._on_spinbox_changed)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)

        painter = QPainter(self)
        x = self._slider.x()
        y = self._slider.y()
        w = self._slider.width()
        h = self._slider.height()
        painter.setClipRect(self._slider.geometry())

        cell = math.ceil(h / 2)
        for cy in range(0, h, cell):
            for cx in range(0, w, cell):
                if (cx // cell + cy // cell) % 2 == 0:
                    painter.fillRect(x + cx, y + cy, cell, cell, QColorConstants.LightGray)
                else:
                    painter.fillRect(x + cx, y + cy, cell, cell, QColorConstants.DarkGray)

    def _on_slider_changed(self, value: int) -> None:
        if self._updating:
            return
        self._updating = True
        self._spinbox.setValue(value)
        self._updating = False
        self.valueChanged.emit(value)

    def _on_spinbox_changed(self, value: int) -> None:
        if self._updating:
            return
        self._updating = True
        self._slider.setValue(value)
        self._updating = False
        self.valueChanged.emit(value)

    def set_value(self, value: int) -> None:
        self._updating = True
        self._slider.setValue(value)
        self._spinbox.setValue(value)
        self._updating = False

    @property
    def value(self) -> int:
        return self._slider.value()

    def set_gradient(self, color_start: QColor, color_end: QColor) -> None:
        start = color_start.name(QColor.NameFormat.HexArgb)
        end = color_end.name(QColor.NameFormat.HexArgb)
        self._slider.setStyleSheet(
            "QSlider::groove:horizontal {"
            "  height: 20px;"
            "  border-radius: 2px;"
            f"  background: qlineargradient(x1:0, y1:0, x2:1, y2:0,"
            f"    stop:0 {start}, stop:1 {end});"
            "}"
            "QSlider::handle:horizontal {"
            "  width: 8px;"
            "  height: 24px;"
            "  margin: -2px 0;"
            "  background: white;"
            "  border: 1px solid black;"
            "  border-radius: 2px;"
            "}"
        )

    def set_rainbow_gradient(self) -> None:
        self._slider.setStyleSheet(
            "QSlider::groove:horizontal {"
            "  height: 20px;"
            "  border-radius: 2px;"
            "  background: qlineargradient(x1:0, y1:0, x2:1, y2:0,"
            "    stop:0 #ff0000, stop:0.167 #ffff00, stop:0.333 #00ff00,"
            "    stop:0.5 #00ffff, stop:0.667 #0000ff, stop:0.833 #ff00ff,"
            "    stop:1 #ff0000);"
            "}"
            "QSlider::handle:horizontal {"
            "  width: 8px;"
            "  height: 24px;"
            "  margin: -2px 0;"
            "  background: white;"
            "  border: 1px solid black;"
            "  border-radius: 2px;"
            "}"
        )


class ColorDialog(QDialog):
    def __init__(
        self,
        initial_color: QColor | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Select Color")
        self._color: QColor = initial_color or QColor(255, 255, 255, 255)
        self._updating = False

        self.resize(400, 300)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self._mode_tabs = QTabWidget()

        self._rgb_container = QWidget()
        rgb_layout = QVBoxLayout(self._rgb_container)
        rgb_layout.setContentsMargins(0, 0, 0, 0)
        rgb_layout.setSpacing(4)

        self._r_slider = ChannelSlider("R", 0, 255)
        self._g_slider = ChannelSlider("G", 0, 255)
        self._b_slider = ChannelSlider("B", 0, 255)
        rgb_layout.addWidget(self._r_slider)
        rgb_layout.addWidget(self._g_slider)
        rgb_layout.addWidget(self._b_slider)

        self._mode_tabs.addTab(self._rgb_container, "RGB")

        self._hsv_container = QWidget()
        hsv_layout = QVBoxLayout(self._hsv_container)
        hsv_layout.setContentsMargins(0, 0, 0, 0)
        hsv_layout.setSpacing(4)

        self._h_slider = ChannelSlider("H", 0, 359)
        self._s_slider = ChannelSlider("S", 0, 255)
        self._v_slider = ChannelSlider("V", 0, 255)
        hsv_layout.addWidget(self._h_slider)
        hsv_layout.addWidget(self._s_slider)
        hsv_layout.addWidget(self._v_slider)

        self._mode_tabs.addTab(self._hsv_container, "HSV")
        layout.addWidget(self._mode_tabs)

        self._a_slider = ChannelSlider("A", 0, 255)
        layout.addWidget(self._a_slider)

        hex_layout = QHBoxLayout()
        hex_label = QLabel("Hex:")
        self._hex_edit = QLineEdit()
        self._hex_edit.setFixedWidth(120)
        hex_layout.addWidget(hex_label)
        hex_layout.addWidget(self._hex_edit)
        hex_layout.addStretch()
        layout.addLayout(hex_layout)

        self._button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        self._button_box.accepted.connect(self.accept)
        self._button_box.rejected.connect(self.reject)
        layout.addWidget(self._button_box)

        self._r_slider.valueChanged.connect(self._on_rgb_changed)
        self._g_slider.valueChanged.connect(self._on_rgb_changed)
        self._b_slider.valueChanged.connect(self._on_rgb_changed)

        self._h_slider.valueChanged.connect(self._on_hsv_changed)
        self._s_slider.valueChanged.connect(self._on_hsv_changed)
        self._v_slider.valueChanged.connect(self._on_hsv_changed)

        self._a_slider.valueChanged.connect(self._on_alpha_changed)
        self._hex_edit.textChanged.connect(self._on_hex_edited)

        self._h_slider.set_rainbow_gradient()
        self._sync_from_color()

    @property
    def selected_color(self) -> QColor:
        return self._color

    def _sync_from_color(self) -> None:
        self._updating = True
        r, g, b, a = self._color.red(), self._color.green(), self._color.blue(), self._color.alpha()
        h, s, v, _ = self._color.getHsvF()
        if h < 0:
            h = 0.0

        self._r_slider.set_value(r)
        self._g_slider.set_value(g)
        self._b_slider.set_value(b)
        self._a_slider.set_value(a)
        self._h_slider.set_value(int(h * 359))
        self._s_slider.set_value(int(s * 255))
        self._v_slider.set_value(int(v * 255))
        self._hex_edit.setText(self._color.name(QColor.NameFormat.HexRgb))
        self._updating = False
        self._update_gradients()

    def _update_color(self, color: QColor) -> None:
        self._color = color
        self._sync_from_color()

    def _update_gradients(self) -> None:
        r, g, b = self._color.red(), self._color.green(), self._color.blue()
        h, s, v, _ = self._color.getHsvF()
        if h < 0:
            h = 0.0

        self._r_slider.set_gradient(QColor(0, g, b), QColor(255, g, b))
        self._g_slider.set_gradient(QColor(r, 0, b), QColor(r, 255, b))
        self._b_slider.set_gradient(QColor(r, g, 0), QColor(r, g, 255))

        self._a_slider.set_gradient(
            QColor(r, g, b, 0),
            QColor(r, g, b, 255),
        )

        s0_color = QColor.fromHsvF(h, 0.0, v)
        s1_color = QColor.fromHsvF(h, 1.0, v)
        self._s_slider.set_gradient(s0_color, s1_color)

        v0_color = QColor.fromHsvF(h, s, 0.0)
        v1_color = QColor.fromHsvF(h, s, 1.0)
        self._v_slider.set_gradient(v0_color, v1_color)

    def _on_rgb_changed(self) -> None:
        if self._updating:
            return

        r = self._r_slider.value
        g = self._g_slider.value
        b = self._b_slider.value
        a = self._a_slider.value
        self._color = QColor(r, g, b, a)
        self._sync_hsv_from_color()
        self._hex_edit.setText(self._color.name(QColor.NameFormat.HexRgb))
        self._update_gradients()

    def _on_hsv_changed(self) -> None:
        if self._updating:
            return
        h = self._h_slider.value / 359.0
        s = self._s_slider.value / 255.0
        v = self._v_slider.value / 255.0
        a = self._a_slider.value
        self._color = QColor.fromHsvF(h, s, v, a / 255.0)
        self._sync_rgb_from_color()
        self._hex_edit.setText(self._color.name(QColor.NameFormat.HexRgb))
        self._update_gradients()

    def _on_alpha_changed(self) -> None:
        if self._updating:
            return
        r, g, b = self._color.red(), self._color.green(), self._color.blue()
        a = self._a_slider.value
        self._color = QColor(r, g, b, a)
        self._hex_edit.setText(self._color.name(QColor.NameFormat.HexRgb))
        self._update_gradients()

    def _sync_rgb_from_color(self) -> None:
        self._updating = True
        self._r_slider.set_value(self._color.red())
        self._g_slider.set_value(self._color.green())
        self._b_slider.set_value(self._color.blue())
        self._updating = False

    def _sync_hsv_from_color(self) -> None:
        self._updating = True
        h, s, v, _ = self._color.getHsvF()
        if h < 0:
            h = 0.0
        self._h_slider.set_value(int(h * 359))
        self._s_slider.set_value(int(s * 255))
        self._v_slider.set_value(int(v * 255))
        self._updating = False

    def _on_hex_edited(self) -> None:
        if self._updating:
            return
        text = self._hex_edit.text().strip()
        if not text.startswith("#"):
            text = "#" + text
        color = QColor(text)
        if color.isValid():
            color.setAlpha(self._a_slider.value)
            self._update_color(color)

