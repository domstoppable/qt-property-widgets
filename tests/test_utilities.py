def test_property_params(mock_property_with_params):
    prop = mock_property_with_params("name", int, min=1, max=10, step=1)

    assert hasattr(prop.fget, "parameters")
    params = prop.fget.parameters

    # Values that were set explicitly are saved
    assert params["min"] == 1
    assert params["max"] == 10
    assert params["step"] == 1

    # Defaults appear for all fields that are left out
    assert params["widget"] == "auto"
