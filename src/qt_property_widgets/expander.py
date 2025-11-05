from PySide6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QSequentialAnimationGroup,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


class Expander(QFrame):
    expanded_changed = Signal(bool)

    def __init__(
        self,
        parent: QWidget | None = None,
        title: str = "",
        content_widget: QWidget | None = None,
        expanded: bool = False,
    ) -> None:
        # Adapted from https://stackoverflow.com/a/56275050
        super().__init__(parent=parent)

        self.content_widget = content_widget
        if content_widget:
            content_widget.setContentsMargins(0, 0, 8, 0)

        self.label = QLabel(title)
        self.label.mousePressEvent = lambda *_: self.expander_button.click()  # type: ignore

        self.expander_button = QToolButton()
        self.expander_button.setCheckable(True)
        self.expander_button.setChecked(expanded)
        self.controls_layout = QHBoxLayout()
        self.controls_layout.addWidget(self.label)
        self.controls_layout.addWidget(self.expander_button)

        self.label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.expander_button.setCursor(Qt.CursorShape.PointingHandCursor)

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 10, 0, 10)
        self.setLayout(layout)

        layout.addLayout(self.controls_layout)
        if self.content_widget:
            layout.addWidget(self.content_widget)

        self.expander_button.clicked.connect(lambda _: self.on_expand_toggled())
        self.expanded = expanded

    def on_expand_toggled(self) -> None:
        if not self.expanded:
            self.expander_button.setText("\uff0d")

            if self.content_widget:
                self.content_widget.show()
                self.content_widget.setSizePolicy(
                    QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum
                )
        else:
            self.expander_button.setText("\uff0b")

            if self.content_widget:
                self.content_widget.hide()

        self.setProperty("expanded", True)
        self.expanded_changed.emit(self.expanded)

    @property
    def expanded(self) -> bool:
        return self.expander_button.isChecked()

    @expanded.setter
    def expanded(self, value: bool) -> None:
        self.expander_button.setChecked(not value)
        self.on_expand_toggled()

    @property
    def title(self) -> str:
        return self.label.text()

    @title.setter
    def title(self, value: str) -> None:
        self.label.setText(value)


class ExpanderList(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent=parent)

        self.container_layout = QVBoxLayout()
        self.container_layout.setSpacing(0)
        self.container_layout.setContentsMargins(5, 5, 5, 5)

        main_layout = QVBoxLayout()

        self.search_widget = QLineEdit()
        self.search_widget.setStyleSheet("margin: 5px; padding: 5px")
        self.search_widget.setPlaceholderText("Search...")
        self.search_widget.setClearButtonEnabled(True)
        self.search_widget.textChanged.connect(self.on_search_text_changed)

        main_layout.addWidget(self.search_widget)
        main_layout.addLayout(self.container_layout)
        main_layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(main_layout)

        self.spacer = QWidget()
        self.spacer.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.container_layout.addWidget(self.spacer)

        self.sort_keys: dict[Expander, str] = {}

    def on_search_text_changed(self, text: str) -> None:
        for item_idx in range(self.container_layout.count()):
            item = self.container_layout.itemAt(item_idx)
            expander = item.widget()
            if isinstance(expander, Expander):
                expander.setVisible(text.lower() in expander.title.lower())

    def add_expander(
        self,
        title: str,
        content: QWidget,
        expanded: bool = False,
        sort_key: str | None = None,
    ) -> Expander:
        expander = Expander(title=title, content_widget=content, expanded=expanded)
        if sort_key is None:
            sort_key = title.lower()

        self.sort_keys[expander] = sort_key

        for item_idx in range(self.container_layout.count() - 1):
            item = self.container_layout.itemAt(item_idx).widget()
            if isinstance(item, Expander):
                key_compare = self.sort_keys[item]
                if key_compare.lower() > sort_key.lower():
                    self.container_layout.insertWidget(item_idx, expander)
                    return expander

        self.container_layout.insertWidget(self.container_layout.count() - 1, expander)

        return expander

    def highlight(
        self,
        expander: Expander,
        duration: float = 0.75,
        min_opacity: float = 0.25,
        max_opacity: float = 1.0,
        blinks: int = 2,
    ) -> None:

        expander.expanded = True

        effect = expander.graphicsEffect()
        if not isinstance(effect, QGraphicsOpacityEffect):
            effect = QGraphicsOpacityEffect(expander)
            effect.setOpacity(1.0)
            expander.setGraphicsEffect(effect)

        fade_out = QPropertyAnimation(effect, b"opacity", expander)
        fade_out.setDuration(duration * 1000 / blinks / 2)
        fade_out.setStartValue(max_opacity)
        fade_out.setEndValue(min_opacity)
        fade_out.setEasingCurve(QEasingCurve.InOutQuad)

        fade_in = QPropertyAnimation(effect, b"opacity", expander)
        fade_in.setDuration(duration * 1000 / blinks / 2)
        fade_in.setStartValue(min_opacity)
        fade_in.setEndValue(max_opacity)
        fade_in.setEasingCurve(QEasingCurve.InOutQuad)

        sequence = QSequentialAnimationGroup()
        sequence.addAnimation(fade_out)
        sequence.addAnimation(fade_in)
        sequence.setLoopCount(blinks)
        self.ensure_visible(expander)
        QTimer.singleShot(250, sequence.start)

        self.anim = sequence

    def ensure_visible(self, expander: Expander) -> None:
        scroll_area = self.find_enclosing_scrollarea()
        if scroll_area:
            scroll_area.ensureWidgetVisible(expander)

    def find_enclosing_scrollarea(self) -> QScrollArea|None:
        w = self
        while w is not None:
            if isinstance(w, QScrollArea):
                return w
            w = w.parentWidget()

        return None

    def remove_expander(self, expander: Expander) -> None:
        del self.sort_keys[expander]

        self.container_layout.removeWidget(expander)
        expander.deleteLater()

    def clear(self) -> None:
        while self.container_layout.count():
            item = self.container_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def count(self) -> int:
        return self.container_layout.count()

    def item_at(self, idx: int) -> QWidget:
        return self.container_layout.itemAt(idx)

    @property
    def searchbar_visibility(self) -> bool:
        return self.search_widget.isVisible()

    @searchbar_visibility.setter
    def searchbar_visibility(self, value: bool) -> None:
        self.search_widget.setVisible(value)
