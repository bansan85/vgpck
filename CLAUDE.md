# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Vcpkg Graphical Package Control Kit (vgpck) — a single-file Tkinter desktop GUI for managing vcpkg binary caches. The entire application lives in [vcpkg-cache.py](vcpkg-cache.py) (~1520 lines); there is no package layout, build system, test suite, or linter configuration in this repo.

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
| 27–113 | `BuildEntry` + `VcpkgArchives` — scans the binary cache and builds the in-memory package/build database |
| 115–186 | `History` — undo/redo stack for the Package comparison tab's combobox state |
| 122–131 | Root window + `Notebook` setup |
| 189–383 | **Package comparison** tab (combos, history wiring) |
| 384–513 | **Remove in vcpkg** tab (formerly "Cleanup") |
| 514–705 | **Remove in cache** tab |
| 706–976 | **Port helper** tab |
| 977–1413 | **CMake arguments** tab |
| 1414–1516 | Diff table + double-click-to-navigate behavior (shared by Package comparison tab) |

### Data model (`VcpkgArchives`)

`VcpkgArchives.read_archives()` recursively globs `*.zip` under the binary cache path. For each archive it expects vcpkg's on-disk layout:
- `BUILD_INFO` entry — its zip timestamp becomes the build's date key.
- `CONTROL` entry — parsed line-by-line for `Package:` and `Abi:` fields.
- `share/<package>/vcpkg_abi_info.txt` (matched case-insensitively) — parsed into arbitrary `key value` pairs.

Results are assembled into `database: Dict[package_name, Dict[date_str, BuildEntry]]`. `BuildEntry` is a `NamedTuple` with two fields: `abi` (a `SimpleNamespace` holding the parsed abi fields as attributes — code that used to read the namespace directly now goes through `.abi`, e.g. `database[pkg][date].abi.triplet`) and `zip_path` (the archive's own `Path`, needed to actually delete it from disk). This nested dict is the single source of truth read by the Package comparison combos, the diff table, and the Remove in cache tab. There's no automatic caching/invalidation — `vcpkg_archives` is built once at startup and never re-scanned — but `VcpkgArchives.delete_build(package, date)`/`delete_package(package)` (used by the Remove in cache tab) mutate `database` in place (unlinking the zip and pruning the now-stale entry/entries) so the in-memory state stays consistent with disk after a deletion.

### Reactive UI pattern (Package comparison tab)

The Package/Date1/Date2/"Same triplet" controls are wired with `tk.Variable.trace_add("write", ...)` callbacks that cascade into each other (e.g. changing the package repopulates the date1 combo's values; changing "same triplet" can clear date2). This is a recurring pattern worth understanding before touching any of these tabs:

- Every user-facing change funnels into `History.save_state(...)`, which pushes a `HistoryStruct(package, date1, date2, same_triplet)` snapshot.
- Navigating history (Previous/Next buttons) replays a snapshot *back into* the same StringVars, which would normally re-trigger the same trace callbacks and push a duplicate history entry.
- `History` guards against this with a re-entrancy counter (`_recurrent_save`): `disabled()`/`enabled()` bracket programmatic writes, and `save_state()` no-ops while the counter is nonzero. When adding new fields to this tab's state, follow the existing pattern (wrap programmatic `.set()` calls in `history.disabled()`/`history.enabled()`, and always end by calling `history.save_state(...)`) or the undo/redo stack will desync.
- The diff table (`update_table`, ~line 1182) re-renders on every `history.trace_add` firing, and double-clicking a differing row (`on_double_click`, ~line 1215) tries to jump history to whichever two build dates produced those two values — it matches by scanning all abi values for an exact string match, so it's a heuristic, not a precise lookup (a value that happens to match across unrelated keys can produce a false jump).

### Remove in vcpkg tab (formerly "Cleanup")

Deletes selected subfolders of a vcpkg install root: `downloads/`, `packages/`, and `buildtrees/`. Note `buildtrees` has two distinct modes that are not mutually exclusive in the UI: "build only" (`cleanup_buildtrees_build_only`) walks `buildtrees/<pkg>/<triplet>/` and removes every triplet subdirectory except one literally named `src`, whereas "build and sources" deletes the entire `buildtrees/` tree. Deletions use `shutil.rmtree(..., ignore_errors=True)` — failures are silent by design (matches existing behavior; don't add error propagation without checking with the user first, since this is a destructive-by-nature feature). Only the tab label and button text ("Remove") are user-facing renames — internal identifiers (`cleanup_frame`, `cleanup_vcpkg`, `cleanup_button`, etc.) are unchanged.

### Remove in cache tab

Deletes archives directly from the vcpkg binary cache (as opposed to the vcpkg install root above), reusing `vcpkg_archives.database` — the same data the Package comparison tab reads. Two `ttk.Treeview` lists emulate a checkable listbox: each row has a `"checked"` column showing a toggle glyph (`☑`/`☐`) alongside the real column (package name or build date), with `removecache_bind_checkbox_toggle()` toggling the glyph on a click in that column while leaving Tk's native row-selection binding to fire afterward — so clicking a row both selects it (`<<TreeviewSelect>>`, distinct from checking) and, if the click landed on the glyph, checks it. The package list (`removecache_package_tree`) drives the build-date list (`removecache_date_tree`) via `refresh_removecache_dates()` on selection change; the date list drives a Key/Value preview table (`removecache_preview_tree`) via `refresh_removecache_preview()`, sourced the same way as the diff table's single-date branch (`vars(database[pkg][date].abi)`).

`remove_from_cache()` (bound to the tab's `Remove` button) has two priorities, matching the spec exactly: if any packages are checked, delete *all* builds for *all* checked packages (`VcpkgArchives.delete_package`, ignoring the date list entirely); otherwise, if a package is selected and dates are checked under it, delete just those builds (`VcpkgArchives.delete_build`). No confirmation dialog — matches the Remove in vcpkg tab's existing silent-delete convention. After any deletion it calls `sync_package_combo_after_delete()`, which refreshes `package_combo`'s values and re-`.set()`s `package_combo_var` (Tk write-traces fire even when the value is unchanged) — this alone cascades through the Package comparison tab's existing `trace_package_combo` → `history.save_state` → `update_table` chain, so that tab's combos/diff table never reference now-deleted data. One accepted side effect: this pushes an extra entry onto that tab's Previous/Next undo stack per deletion, even when unrelated to what it's currently showing.

### Port helper tab

Builds a download URL + auth headers for a Github release/ref archive, a Gitlab archive, or a direct URL (`build_port_helper_url`), downloads it to a temp file while streaming through `hashlib.sha512()`, and surfaces the resulting SHA512 for pasting into a vcpkg `portfile.cmake`. Entry fields use a manual placeholder-text pattern (`apply_placeholder`/`get_trimmed`) since Tkinter has no native placeholder support — treat the placeholder string as "empty" wherever these vars are read.

### CMake arguments tab

Two independent discovery steps feed the generated command:
- `get_triplets_from_vcpkg` / `get_triplets_from_registry` glob `triplets/*.cmake` (and, for registries, any nested `triplets/` folder) to populate the target/host triplet combos.
- `detect_cmake_options` regex-scans every `CMakeLists.txt` under the selected project for `option(NAME "help" DEFAULT)` and `set(NAME VALUE ... CACHE ...)` calls, then dynamically builds a checkbox (for `option()`) or text entry (for `set()`) per discovered name in `detected_options_frame`. This is regex-based, not a real CMake parser — it won't handle every possible CMake syntax edge case, so keep changes here narrowly scoped to what the existing patterns already match.

`make_cmake_command()` is the single place that assembles output from all of the above plus the fixed well-known flags (`BUILD_SHARED_LIBS`, `CMAKE_EXPORT_COMPILE_COMMANDS`, `BUILD_TESTING`, `CMAKE_INSTALL_PREFIX`), and renders it either as a `cmake ...` command line or as a `"cmake.configureArgs": [...]` JSON snippet for VSCode's `settings.json`. Every relevant Tkinter variable has a `trace_add` wired to call `make_cmake_command()`, so the output box is always kept live — if you add a new option/flag, remember to wire its trace the same way.
