"""qt_property_widgets package."""

from __future__ import annotations

import importlib.metadata
from importlib import resources
from pathlib import Path

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"


def asset_path(resource: str) -> Path:
    package_assets_path = resources.files(__package__).joinpath("assets")
    with resources.as_file(package_assets_path) as assets_path:
        return assets_path / resource


__all__: list[str] = ["__version__", "asset_path"]
