import os
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
KOBRA_EXAMPLE = ROOT / "examples" / "profiles" / "kobra2max"
MODELS = Path(__file__).parent / "models"

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


@pytest.fixture(scope="session")
def vendor_datadir(install, tmp_path_factory) -> Path:
    """Temporary datadir with the Prusa vendor bundle and the MK4S 0.4 installed."""
    if install.resources is None:
        pytest.skip("Instalación sin carpeta resources")
    d = tmp_path_factory.mktemp("datadir_vendor")
    (d / "vendor").mkdir()
    shutil.copy(install.resources / "profiles" / "PrusaResearch.ini", d / "vendor" / "PrusaResearch.ini")
    (d / "PrusaSlicer.ini").write_text("[vendor:PrusaResearch]\nmodel:MK4S = 0.4\n", encoding="utf-8")
    return d


@pytest.fixture
def kobra_datadir(tmp_path) -> Path:
    """Temporary datadir with only the Kobra 2 MAX example user presets."""
    d = tmp_path / "datadir_kobra"
    shutil.copytree(KOBRA_EXAMPLE, d, ignore=shutil.ignore_patterns("README.md"))
    (d / "PrusaSlicer.ini").write_text("", encoding="utf-8")
    return d
