# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Vcpkg Graphical Package Control Kit (vgpck) — a single-file Tkinter desktop GUI for managing vcpkg binary caches. The entire application lives in [vcpkg-cache.py](vcpkg-cache.py) (~1270 lines); there is no package layout, build system, test suite, or linter configuration in this repo.

## Running the app

```bash
python vcpkg-cache.py
```

Requirements:
- Python 3.7+ (stdlib only — `tkinter`, `zipfile`, `urllib.request`, `hashlib`, etc. No `requirements.txt`, no third-party dependencies).
- The `VCPKG_DEFAULT_BINARY_CACHE` environment variable **must** be set to a directory containing vcpkg's cached `*.zip` archives before launching — the script checks this at import time (top of the file) and calls `sys.exit(0)` immediately if it's unset. When testing locally, point it at a real vcpkg binary cache directory (or a directory of test `.zip` fixtures shaped like vcpkg archives — see "Data model" below for the expected internal layout).

There is no automated test suite, lint config, or CI in this repo. Verify changes by running the app manually and exercising the relevant tab.

## Architecture

Everything is one flat, sequential script — there are no functions/classes split across modules. Code is organized into contiguous sections, each building one `ttk.Notebook` tab and wiring its own Tkinter variables and callbacks in place (imperative UI construction, not a separate "app" object). When navigating the file, use these approximate regions:

| Lines | Section |
|---|---|
| 27–93 | `VcpkgArchives` — scans the binary cache and builds the in-memory package/build database |
| 86–157 | `History` — undo/redo stack for the Package comparison tab's combobox state |
| 95–103 | Root window + `Notebook` setup |
| 105–352 | **Package comparison** tab (combos, history wiring) |
| 355–456 | **Cleanup** tab |
| 458–727 | **Port helper** tab |
| 729–1164 | **CMake arguments** tab |
| 1166–1266 | Diff table + double-click-to-navigate behavior (shared by Package comparison tab) |

### Data model (`VcpkgArchives`)

`VcpkgArchives.read_archives()` recursively globs `*.zip` under the binary cache path. For each archive it expects vcpkg's on-disk layout:
- `BUILD_INFO` entry — its zip timestamp becomes the build's date key.
- `CONTROL` entry — parsed line-by-line for `Package:` and `Abi:` fields.
- `share/<package>/vcpkg_abi_info.txt` (matched case-insensitively) — parsed into arbitrary `key value` pairs.

Results are assembled into `database: Dict[package_name, Dict[date_str, SimpleNamespace]]`, where each `SimpleNamespace` holds the abi fields as attributes. This nested dict is the single source of truth read by both the Package comparison combos and the diff table — there's no caching/invalidation, so `vcpkg_archives` is built once at startup and never refreshed.

### Reactive UI pattern (Package comparison tab)

The Package/Date1/Date2/"Same triplet" controls are wired with `tk.Variable.trace_add("write", ...)` callbacks that cascade into each other (e.g. changing the package repopulates the date1 combo's values; changing "same triplet" can clear date2). This is a recurring pattern worth understanding before touching any of these tabs:

- Every user-facing change funnels into `History.save_state(...)`, which pushes a `HistoryStruct(package, date1, date2, same_triplet)` snapshot.
- Navigating history (Previous/Next buttons) replays a snapshot *back into* the same StringVars, which would normally re-trigger the same trace callbacks and push a duplicate history entry.
- `History` guards against this with a re-entrancy counter (`_recurrent_save`): `disabled()`/`enabled()` bracket programmatic writes, and `save_state()` no-ops while the counter is nonzero. When adding new fields to this tab's state, follow the existing pattern (wrap programmatic `.set()` calls in `history.disabled()`/`history.enabled()`, and always end by calling `history.save_state(...)`) or the undo/redo stack will desync.
- The diff table (`update_table`, ~line 1182) re-renders on every `history.trace_add` firing, and double-clicking a differing row (`on_double_click`, ~line 1215) tries to jump history to whichever two build dates produced those two values — it matches by scanning all abi values for an exact string match, so it's a heuristic, not a precise lookup (a value that happens to match across unrelated keys can produce a false jump).

### Cleanup tab

Deletes selected subfolders of a vcpkg install root: `downloads/`, `packages/`, and `buildtrees/`. Note `buildtrees` has two distinct modes that are not mutually exclusive in the UI: "build only" (`cleanup_buildtrees_build_only`) walks `buildtrees/<pkg>/<triplet>/` and removes every triplet subdirectory except one literally named `src`, whereas "build and sources" deletes the entire `buildtrees/` tree. Deletions use `shutil.rmtree(..., ignore_errors=True)` — failures are silent by design (matches existing behavior; don't add error propagation without checking with the user first, since this is a destructive-by-nature feature).

### Port helper tab

Builds a download URL + auth headers for a Github release/ref archive, a Gitlab archive, or a direct URL (`build_port_helper_url`), downloads it to a temp file while streaming through `hashlib.sha512()`, and surfaces the resulting SHA512 for pasting into a vcpkg `portfile.cmake`. Entry fields use a manual placeholder-text pattern (`apply_placeholder`/`get_trimmed`) since Tkinter has no native placeholder support — treat the placeholder string as "empty" wherever these vars are read.

### CMake arguments tab

Two independent discovery steps feed the generated command:
- `get_triplets_from_vcpkg` / `get_triplets_from_registry` glob `triplets/*.cmake` (and, for registries, any nested `triplets/` folder) to populate the target/host triplet combos.
- `detect_cmake_options` regex-scans every `CMakeLists.txt` under the selected project for `option(NAME "help" DEFAULT)` and `set(NAME VALUE ... CACHE ...)` calls, then dynamically builds a checkbox (for `option()`) or text entry (for `set()`) per discovered name in `detected_options_frame`. This is regex-based, not a real CMake parser — it won't handle every possible CMake syntax edge case, so keep changes here narrowly scoped to what the existing patterns already match.

`make_cmake_command()` is the single place that assembles output from all of the above plus the fixed well-known flags (`BUILD_SHARED_LIBS`, `CMAKE_EXPORT_COMPILE_COMMANDS`, `BUILD_TESTING`, `CMAKE_INSTALL_PREFIX`), and renders it either as a `cmake ...` command line or as a `"cmake.configureArgs": [...]` JSON snippet for VSCode's `settings.json`. Every relevant Tkinter variable has a `trace_add` wired to call `make_cmake_command()`, so the output box is always kept live — if you add a new option/flag, remember to wire its trace the same way.
