import os

import pytest

from prusaslicer_mcp.errors import SlicerNotFoundError
from prusaslicer_mcp.install import find_installation


@pytest.fixture(scope="session")
def install():
    try:
        return find_installation()
    except SlicerNotFoundError as e:
        if os.environ.get("PRUSASLICER_REQUIRE") == "1":
            pytest.fail(f"PrusaSlicer requerido pero no encontrado: {e.message}")
        pytest.skip("PrusaSlicer no instalado")
