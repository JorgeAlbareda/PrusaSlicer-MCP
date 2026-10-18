# PrusaSlicer-MCP

An **unofficial** [Model Context Protocol](https://modelcontextprotocol.io) server that lets AI assistants
(Claude Desktop, Claude Code or any MCP client) drive [PrusaSlicer](https://github.com/prusa3d/PrusaSlicer):
pick profiles, place models, slice, analyse the G-code and send it to a networked printer.

> **Not affiliated with Prusa Research.** "PrusaSlicer" is a trademark of Prusa Research a.s.
> This project drives the official, open-source PrusaSlicer (AGPL-3.0).

| Version | Engine | Status |
|---|---|---|
| **v1** | Official `prusa-slicer-console` (command line) | ✅ this release — Windows tested |
| v2 | Patched PrusaSlicer with a local bridge: changes appear **live** in the PrusaSlicer window | planned |

## What it does

- Uses **your own PrusaSlicer profiles** (system profiles of any vendor and your user profiles) by name.
- Keeps a **bed session**: add models, rotate/scale, copies, fixed positions or automatic arrangement.
- **Verified slicing**: every G-code is checked against the configuration that was asked for
  (profile ids, every changed setting and critical keys such as bed shape, nozzle, temperatures).
  If PrusaSlicer silently used something else, the slice fails instead of handing you a wrong file.
- **G-code analytics**: time and material per move type (perimeters, infill, bridges, travel…) and
  **print-risk detection** (warping, overhangs, long bridges, volumetric flow, machine limits,
  short layers…), each with its evidence and whether it is a measured violation or a heuristic.
- Opens results in your PrusaSlicer window or the G-code viewer.
- Uploads to **OctoPrint, Moonraker (Klipper) and PrusaLink** printers configured in PrusaSlicer.

## Requirements

- PrusaSlicer **2.9.x** installed (tested with 2.9.4 and 2.9.6).
- [uv](https://docs.astral.sh/uv/) (or Python ≥ 3.11).

## Install

Claude Code:

```bash
claude mcp add prusaslicer -- uvx --from git+https://github.com/JorgeAlbareda/PrusaSlicer-MCP prusaslicer-mcp
```

Claude Desktop (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "prusaslicer": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/JorgeAlbareda/PrusaSlicer-MCP", "prusaslicer-mcp"]
    }
  }
}
```

## Configuration (environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `PRUSASLICER_PATH` | standard install folders | Folder containing `prusa-slicer-console` |
| `PRUSASLICER_DATADIR` | `%APPDATA%\PrusaSlicer` (Windows) | PrusaSlicer configuration folder with your profiles |
| `PRUSASLICER_MCP_WORKDIR` | `<temp>/prusaslicer-mcp` | Where G-code and intermediate files are written |
| `PRUSASLICER_MCP_ALLOW_PRINT_CONTROL` | off | `1` enables start / pause / resume / cancel on printers |
| `PRUSASLICER_MCP_ALLOW_POST_PROCESS` | off | `1` lets profiles run their `post_process` scripts |

## Tools

| Group | Tools | v1 | v2 |
|---|---|---|---|
| Info & profiles | `get_slicer_info`, `list_printers`, `list_compatible_profiles`, `select_profiles`, `use_config_file` | ✓ | ✓ |
| Settings | `get_setting`, `set_setting`, `reset_setting`, `save_profile_as`, `import_profile_bundle` | ✓ | ✓ |
| Bed | `add_model`, `get_plate`, `remove_object`, `clear_plate`, `transform_object`, `place_instance`, `arrange_plate` | ✓ | ✓ |
| Slicing | `slice`, `export_3mf` | ✓ | ✓ |
| Analysis | `get_gcode_metrics`, `analyze_toolpaths`, `find_print_risks` | ✓ | ✓ |
| View | `show_in_slicer` | ✓ | ✓ |
| View/optimise (live) | `preview_layer`, `set_variable_layer_height`, `add_height_range_modifier` | — | ✓ |
| Printers | `list_print_hosts`, `upload_gcode`, `get_printer_status` | ✓ | ✓ |
| Print control | `start_print`, `pause_print`, `resume_print`, `cancel_print` | ✓* | ✓* |

\* Disabled unless the user sets `PRUSASLICER_MCP_ALLOW_PRINT_CONTROL=1`.

## Safety

- **Printer control is off by default.** When enabled, every start/pause/resume/cancel asks the human:
  through MCP *elicitation* when the client supports it, otherwise with a one-time code (2 minutes,
  bound to that printer and that job) that the assistant must only use after you say yes. The
  code-based flow relies on the client/assistant asking you; that is why control is opt-in.
- **External programs are blocked.** PrusaSlicer runs the `post_process` setting after export; the
  server forces it empty unless you opt in, and strips it from imported bundles.
- Your profiles are never overwritten without `overwrite=true`, and a timestamped backup is kept.
- G-code is always text (not binary `.bgcode`) so it can be analysed.

## Example profiles

`examples/profiles/kobra2max/` contains corrected PrusaSlicer 2.9 profiles for the Anycubic Kobra 2 MAX.

## Development

```bash
uv sync
uv run pytest            # tests marked `slicer` need PrusaSlicer installed (skipped otherwise)
```

Design and plans: [`docs/superpowers/specs`](docs/superpowers/specs), [`docs/superpowers/plans`](docs/superpowers/plans).
Spanish usage guide: [`docs/usage.md`](docs/usage.md).

## Roadmap

- **v2** — PrusaSlicer 2.9 built with a small patch set (`patches/`) that embeds a localhost bridge, so the
  same tools act on the open PrusaSlicer window in real time (live preview, adaptive layer height,
  height-range modifiers). Windows first.
- macOS and Linux support.

## License

AGPL-3.0-only. See [LICENSE](LICENSE). Test models in `tests/models` come from the PrusaSlicer repository (AGPL-3.0).
