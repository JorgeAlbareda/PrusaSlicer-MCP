import sys
from pathlib import Path

import pytest

from prusaslicer_mcp.errors import CliError, CliTimeoutError
from prusaslicer_mcp.install import SlicerInstall
from prusaslicer_mcp.runner import classify_output, run_cli

REMOVED_KEYS = (
    "[2026-10-18 14:50:09.072581] [0x00003120] [error]   Error in a preset file: The preset "
    '"C:\\dd\\printer\\K2M Printer.ini" contains the following incorrect keys: extrusion_axis, '
    "which were removed"
)
STABILITY = (
    "Print warning: Detected print stability issues:\n\n3DBenchy.stl\nLow bed adhesion\n\n"
    "Consider enabling supports.\nAlso consider enabling brim."
)


def _python_install() -> SlicerInstall:
    return SlicerInstall(console=Path(sys.executable), gui=None, gcodeviewer=None, resources=None, version="0")


def test_removed_keys_is_warning():
    warnings, errors = classify_output(REMOVED_KEYS)
    assert errors == []
    assert len(warnings) == 1 and "extrusion_axis" in warnings[0]


def test_stability_block_is_one_warning():
    text = "10 => Processing triangulated mesh\n" + STABILITY + "\nSlicing result exported to x.gcode\n"
    warnings, errors = classify_output(text)
    assert errors == []
    assert len(warnings) == 1
    assert "Low bed adhesion" in warnings[0] and "Consider enabling supports." in warnings[0]


def test_profile_not_found_is_error():
    warnings, errors = classify_output(
        "Error while loading config from profiles: \nPrint profile '0.20mm SPEED @PG' wasn't found.\n"
    )
    assert any("wasn't found" in e for e in errors)


def test_g92_incompatible_is_error():
    _, errors = classify_output(
        '"G92 E0" was found in before_layer_gcode, which is incompatible with absolute extruder addressing.\n'
    )
    assert len(errors) == 1


def test_progress_lines_dropped():
    assert classify_output("10 => Processing triangulated mesh\n90 => Exporting G-code\n") == ([], [])


def test_run_cli_ok():
    res = run_cli(_python_install(), ["-c", "print('hola')"], timeout=30)
    assert res.returncode == 0 and "hola" in res.stdout


def test_run_cli_nonzero_raises():
    with pytest.raises(CliError) as e:
        run_cli(_python_install(), ["-c", "import sys; print(\"Print profile 'X' wasn't found.\"); sys.exit(1)"])
    assert "wasn't found" in e.value.message


def test_run_cli_timeout():
    with pytest.raises(CliTimeoutError):
        run_cli(_python_install(), ["-c", "import time; time.sleep(10)"], timeout=1)
