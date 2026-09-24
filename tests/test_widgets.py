from qt_property_widgets.widgets import SpinboxWidget


def test_float_property_widget_no_range(widget_for_mock_property):
    widget, _ = widget_for_mock_property("name", float)

    assert isinstance(widget, SpinboxWidget)
    assert widget.spinbox.isVisible()
    assert not widget.slider.isVisible()


def test_float_property_widget_has_range(widget_for_mock_property):
    widget, _ = widget_for_mock_property("name", float, min=1.0, max=10.0)

    assert isinstance(widget, SpinboxWidget)
    assert widget.spinbox.isVisible()
    assert widget.slider.isVisible()


def test_float_property_widget_no_spinbox(widget_for_mock_property):
    widget, _ = widget_for_mock_property("name", float, show_spinbox=False)

    assert isinstance(widget, SpinboxWidget)
    assert not widget.spinbox.isVisible()


def test_float_property_widget_decimals(widget_for_mock_property):
    widget, _ = widget_for_mock_property(
        "name", float, min=0.01, max=0.05, step=0.02, decimals=2
    )

    assert isinstance(widget, SpinboxWidget)
    assert widget.slider.minimum() == 1
    assert widget.slider.maximum() == 5
    assert widget.slider.singleStep() == 2
