from pathlib import Path
import sys
from zipfile import ZipFile
from datetime import datetime
from typing import Optional, Dict, List
import re
import json
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import os
import shutil
from typing import NamedTuple
from types import SimpleNamespace
from collections.abc import Callable

binary_cache = os.getenv("VCPKG_DEFAULT_BINARY_CACHE")
if binary_cache is None:  # type: ignore
    print("VCPKG_DEFAULT_BINARY_CACHE environment variable is not set.")
    sys.exit(0)


class VcpkgArchives:
    def __init__(self, path: str):
        self.path = path
        self.read_archives()

    def read_archives(self):
        zip_files = list(Path(self.path).rglob("*.zip"))
        # Dict[package_name, Dict[date_of_build, abi_field]]
        database: Dict[str, Dict[str, SimpleNamespace]] = {}
        for f in zip_files:
            with ZipFile(f, "r") as zf:
                info = zf.getinfo("BUILD_INFO")
                dt = datetime(*info.date_time).strftime("%Y-%m-%d %H:%M:%S")

                content = zf.read("CONTROL").decode("utf-8")

                package_name: Optional[str] = None
                abi: Optional[str] = None
                for line in content.split("\n"):
                    if line.startswith("Package:"):
                        package_name = line.split(":", 1)[1].strip()
                    if line.startswith("Abi:"):
                        abi = line.split(":", 1)[1].strip()

                assert package_name is not None
                assert abi is not None

                # Read vcpkg_abi_info.txt
                abi_path = [
                    n
                    for n in zf.namelist()
                    if n.lower().endswith(
                        f"share/{package_name.lower()}/vcpkg_abi_info.txt".lower()
                    )
                ][0]
                abi_content = zf.read(abi_path).decode("utf-8")

                # Parse to dict
                abi_dict = {}
                abi_dict["abi"] = abi
                for line in abi_content.split("\n"):
                    if line.strip():
                        key, value = line.split(None, 1)
                        abi_dict[key] = value

                if package_name not in database:
                    database[package_name] = {}
                database[package_name][dt] = SimpleNamespace(**abi_dict)

        self.database = database

    def sorted_packages(self):
        return sorted(list(self.database.keys()))

    def get_dates(self, package: str):
        dates = sorted(vcpkg_archives.database[package].keys())
        return [d for d in dates]


class HistoryStruct(NamedTuple):
    package: str
    date1: str
    date2: str
    same_triplet: bool


vcpkg_archives = VcpkgArchives(binary_cache)

root = tk.Tk()

notebook = ttk.Notebook(root)
package_frame = ttk.Frame(notebook)
cleanup_frame = ttk.Frame(notebook)
notebook.add(package_frame, text="Package comparison")
notebook.add(cleanup_frame, text="Cleanup")
notebook.pack(expand=True, fill="both")


class History:
    def __init__(self):
        self.stack: List[HistoryStruct] = [
            HistoryStruct(package="", date1="", date2="", same_triplet=False)
        ]
        self.history_index = tk.IntVar(value=0)
        self._recurrent_save = 0

    def save_state(self, state: HistoryStruct):
        if self._recurrent_save != 0:
            return
        self.stack[self.history_index.get() + 1 :] = []
        self.stack.append(state)
        self._recurrent_save += 1
        self.history_index.set(len(self.stack) - 1)
        self._recurrent_save -= 1

    def length(self):
        return len(self.stack)

    def current(self):
        return self.stack[self.history_index.get()]

    def get(self, i: int):
        return self.stack[i]

    def increment(self):
        self._recurrent_save += 1
        self.history_index.set(self.history_index.get() + 1)
        self._recurrent_save -= 1

    def decrement(self):
        self._recurrent_save += 1
        self.history_index.set(self.history_index.get() - 1)
        self._recurrent_save -= 1

    def disabled(self):
        self._recurrent_save += 1

    def enabled(self):
        self._recurrent_save -= 1

    def can_increment(self):
        return self.history_index.get() >= self.length() - 1

    def can_decrement(self):
        return self.history_index.get() < 1

    def trace_add(self, callback: Callable[[str, str, str], object]):
        self.history_index.trace_add("write", callback=callback)


history = History()


root.title("Vcpkg Graphical Package Control Kit")
root.geometry("800x600")


def trace_prev_button_state(var: str, index: str, mode: str):
    prev_button.configure(state="normal" if history.can_decrement() < 1 else "disabled")


def trace_next_button_state(var: str, index: str, mode: str):
    next_button.configure(state="normal" if not history.can_increment() else "disabled")


prev_button = tk.Button(
    package_frame, text="< Previous", command=lambda: history.decrement()
)
prev_button.grid(row=0, column=2, padx=5, pady=5)
prev_button.configure(state="disabled")
history.trace_add(trace_prev_button_state)
next_button = tk.Button(
    package_frame, text="Next >", command=lambda: history.increment()
)
next_button.grid(row=0, column=3, padx=5, pady=5)
next_button.configure(state="disabled")
history.trace_add(trace_next_button_state)

tk.Label(package_frame, text="Package:").grid(row=0, column=0, padx=5, pady=5)
package_combo_var = tk.StringVar(value="")
package_combo = ttk.Combobox(
    package_frame,
    values=vcpkg_archives.sorted_packages(),
    state="readonly",
    textvariable=package_combo_var,
)
package_combo.grid(row=0, column=1, padx=5, pady=5)


def trace_package_combo(var: str, index: str, mode: str):
    pkg = package_combo_var.get()
    _, date1_str, date2_str, triplet = history.current()
    history.disabled()
    if pkg and pkg in vcpkg_archives.database:
        date1_combo["values"] = vcpkg_archives.get_dates(pkg)
    if (
        not pkg in vcpkg_archives.database
        or not date1_str in vcpkg_archives.database[pkg]
    ):
        date1_combo_var.set("")
        date1_str = ""
    if (
        not pkg in vcpkg_archives.database
        or not date2_str in vcpkg_archives.database[pkg]
    ):
        date2_combo_var.set("")
        date2_str = ""
    history.enabled()
    history.save_state(
        HistoryStruct(
            package=pkg,
            date1=date1_str,
            date2=date2_str,
            same_triplet=triplet,
        )
    )


def trace_package_combo_form_history_index(var: str, index: str, mode: str):
    package_combo_var.set(history.current().package)


package_combo_var.trace_add(mode="write", callback=trace_package_combo)
history.trace_add(trace_package_combo_form_history_index)

tk.Label(package_frame, text="Date 1:").grid(row=1, column=0, padx=5, pady=5)
date1_combo_var = tk.StringVar(value="")
date1_combo = ttk.Combobox(
    package_frame, state="readonly", textvariable=date1_combo_var
)
date1_combo.grid(row=1, column=1, padx=5, pady=5)


def trace_date1_combo(var: str, index: str, mode: str):
    date1_str = date1_combo_var.get()
    pkg, _, date2_str, triplet = history.current()

    history.disabled()
    if (
        not pkg in vcpkg_archives.database
        or not date2_str in vcpkg_archives.database[pkg]
    ):
        date2_combo_var.set("")
        date2_str = ""
    dates: List[str] = list(date1_combo["values"])
    if data2_same_triplet_var.get() and date1_str != "":
        date_strs = [
            d
            for d in dates
            if vcpkg_archives.database[pkg][date1_str].triplet
            == vcpkg_archives.database[pkg][d].triplet
        ]
        if (
            date2_str in vcpkg_archives.database[pkg]
            and vcpkg_archives.database[pkg][date2_str].triplet
            != vcpkg_archives.database[pkg][date1_str].triplet
        ):
            date2_combo_var.set("")
            date2_str = ""

    else:
        date_strs = dates
    date_strs.insert(0, "")
    date2_combo["values"] = date_strs
    history.enabled()
    history.save_state(
        HistoryStruct(
            package=pkg,
            date1=date1_str,
            date2=date2_str,
            same_triplet=triplet,
        )
    )


def trace_date1_combo_form_history_index(var: str, index: str, mode: str):
    date1_combo_var.set(history.current().date1)


date1_combo_var.trace_add(mode="write", callback=trace_date1_combo)
history.trace_add(trace_date1_combo_form_history_index)


tk.Label(package_frame, text="Date 2:").grid(row=2, column=0, padx=5, pady=5)
date2_combo_var = tk.StringVar(value="")
date2_combo = ttk.Combobox(
    package_frame, state="readonly", textvariable=date2_combo_var
)
date2_combo.grid(row=2, column=1, padx=5, pady=5)


def trace_date2_combo(var: str, index: str, mode: str):
    history.save_state(
        HistoryStruct(
            package=package_combo_var.get(),
            date1=date1_combo_var.get(),
            date2=date2_combo_var.get(),
            same_triplet=data2_same_triplet_var.get(),
        )
    )


def trace_date2_combo_form_history_index(var: str, index: str, mode: str):
    date2_combo_var.set(history.current().date2)


date2_combo_var.trace_add(mode="write", callback=trace_date2_combo)
history.trace_add(trace_date2_combo_form_history_index)


data2_same_triplet_var = tk.BooleanVar(value=False)
data2_same_triplet = ttk.Checkbutton(
    package_frame, text="Same triplet", variable=data2_same_triplet_var
)
data2_same_triplet.grid(row=2, column=2, padx=5, pady=5)


def trace_same_triplet(var: str, index: str, mode: str):
    if (
        data2_same_triplet_var.get()
        and date1_combo_var.get() != ""
        and date2_combo_var.get() != ""
        and vcpkg_archives.database[package_combo_var.get()][
            date1_combo_var.get()
        ].triplet
        != vcpkg_archives.database[package_combo_var.get()][
            date2_combo_var.get()
        ].triplet
    ):
        date2_combo_var.set("")
    history.save_state(
        HistoryStruct(
            package=package_combo_var.get(),
            date1=date1_combo_var.get(),
            date2=date2_combo_var.get(),
            same_triplet=data2_same_triplet_var.get(),
        )
    )


def trace_same_triplet_form_history_index(var: str, index: str, mode: str):
    data2_same_triplet_var.set(history.current().same_triplet)


data2_same_triplet_var.trace_add(mode="write", callback=trace_same_triplet)
history.trace_add(trace_same_triplet_form_history_index)


# Cleanup tab
vcpkg_path_var = tk.StringVar(value="")


def choose_vcpkg_path():
    selected = filedialog.askdirectory(title="Select vcpkg folder")
    if selected:
        vcpkg_path_var.set(selected)


def cleanup_buildtrees_build_only(vcpkg_path: Path):
    buildtrees_path = vcpkg_path / "buildtrees"
    if not buildtrees_path.exists():
        return
    for pkg_dir in buildtrees_path.iterdir():
        if not pkg_dir.is_dir():
            continue
        for triplet_dir in pkg_dir.iterdir():
            if not triplet_dir.is_dir():
                continue
            if triplet_dir.name == "src":
                continue
            shutil.rmtree(triplet_dir, ignore_errors=True)


def cleanup_vcpkg():
    path = vcpkg_path_var.get().strip()
    if not path:
        messagebox.showwarning("Missing path", "Please enter the vcpkg folder path.")
        return
    vcpkg_path = Path(path)
    if not vcpkg_path.exists() or not vcpkg_path.is_dir():
        messagebox.showerror("Erreur", "vcpkg folder doesn't exists.")
        return

    choices: list[str] = []
    if downloads_var.get():
        downloads_path = vcpkg_path / "downloads"
        if downloads_path.exists():
            shutil.rmtree(downloads_path, ignore_errors=True)
            choices.append("downloads")
    if packages_var.get():
        packages_path = vcpkg_path / "packages"
        if packages_path.exists():
            shutil.rmtree(packages_path, ignore_errors=True)
            choices.append("packages")
    if buildtrees_build_only_var.get():
        cleanup_buildtrees_build_only(vcpkg_path)
        choices.append("buildtrees (build only)")
    if buildtrees_build_and_sources_var.get():
        buildtrees_path = vcpkg_path / "buildtrees"
        if buildtrees_path.exists():
            shutil.rmtree(buildtrees_path, ignore_errors=True)
            choices.append("buildtrees (build and sources)")

    message = "Done."
    if choices:
        message += "\nItems deleted : " + ", ".join(choices)
    else:
        message += "\nNo items selected."
    messagebox.showinfo("Completed", message)


vcpkg_label = tk.Label(cleanup_frame, text="vcpkg path :")
vcpkg_label.grid(row=0, column=0, padx=5, pady=5, sticky="w")

vcpkg_entry = tk.Entry(cleanup_frame, textvariable=vcpkg_path_var, width=60)
vcpkg_entry.grid(row=0, column=1, padx=5, pady=5, sticky="we")

browse_btn = tk.Button(cleanup_frame, text="Browse...", command=choose_vcpkg_path)
browse_btn.grid(row=0, column=2, padx=5, pady=5)


downloads_var = tk.BooleanVar(value=False)
buildtrees_build_only_var = tk.BooleanVar(value=False)
buildtrees_build_and_sources_var = tk.BooleanVar(value=False)
packages_var = tk.BooleanVar(value=False)

cb_downloads = tk.Checkbutton(cleanup_frame, text="downloads", variable=downloads_var)
cb_downloads.grid(row=1, column=0, columnspan=3, padx=5, pady=5, sticky="w")

cb_buildtrees_only = tk.Checkbutton(
    cleanup_frame,
    text="buildtrees (build only)",
    variable=buildtrees_build_only_var,
)
cb_buildtrees_only.grid(row=2, column=0, columnspan=3, padx=5, pady=5, sticky="w")

cb_buildtrees_both = tk.Checkbutton(
    cleanup_frame,
    text="buildtrees (build and sources)",
    variable=buildtrees_build_and_sources_var,
)
cb_buildtrees_both.grid(row=3, column=0, columnspan=3, padx=5, pady=5, sticky="w")

cb_packages = tk.Checkbutton(cleanup_frame, text="packages", variable=packages_var)
cb_packages.grid(row=4, column=0, columnspan=3, padx=5, pady=5, sticky="w")

cleanup_button = tk.Button(cleanup_frame, text="Cleanup", command=cleanup_vcpkg)
cleanup_button.grid(row=5, column=0, columnspan=3, padx=5, pady=10)

cleanup_frame.grid_columnconfigure(1, weight=1)

# CMake tab
cmake_frame = ttk.Frame(notebook)
notebook.add(cmake_frame, text="CMake arguments")

cmake_project_path_var = tk.StringVar(value="")
cmake_vcpkg_path_var = tk.StringVar(value="")
cmake_target_triplet_var = tk.StringVar(value="")
cmake_host_triplet_var = tk.StringVar(value="")
cmake_host_same_var = tk.BooleanVar(value=True)
cmake_build_shared_var = tk.BooleanVar(value=False)
cmake_export_compile_commands_var = tk.BooleanVar(value=False)
cmake_build_testing_var = tk.BooleanVar(value=False)
cmake_install_prefix_var = tk.StringVar(value="")
cmake_registry_paths: List[str] = []
cmake_detected_options_vars: Dict[str, tk.Variable] = {}
cmake_detected_options_types: Dict[str, str] = {}
cmake_detected_options_defaults: Dict[str, str] = {}
cmake_output_format_var = tk.StringVar(value="command")

# common next values
cmake_triplets: List[str] = []


def get_triplets_from_vcpkg(vcpkg_path_str: str) -> List[str]:
    triplets: set[str] = set()
    if not vcpkg_path_str:
        return []
    p = Path(vcpkg_path_str)
    if not p.exists():
        return []
    for candidates in [p / "triplets", p / "triplets" / "community"]:
        if candidates.exists() and candidates.is_dir():
            for f in candidates.glob("*.cmake"):
                triplets.add(f.stem)
    return sorted(triplets)


def get_triplets_from_registry(registry_path_str: str) -> List[str]:
    triplets: set[str] = set()
    if not registry_path_str:
        return []
    p = Path(registry_path_str)
    if not p.exists():
        return []
    for dirpath in [p / "triplets", p / "vcpkg-registry" / "triplets"]:
        if dirpath.exists() and dirpath.is_dir():
            for f in dirpath.glob("*.cmake"):
                triplets.add(f.stem)
    # also search recursively for nested triplets folders in registry layouts
    for triplets_path in p.rglob("triplets"):
        if triplets_path.is_dir():
            for f in triplets_path.glob("*.cmake"):
                triplets.add(f.stem)
    return sorted(triplets)


def refresh_triplets():
    all_triplets = set(get_triplets_from_vcpkg(cmake_vcpkg_path_var.get()))
    for rp in cmake_registry_paths:
        all_triplets.update(get_triplets_from_registry(rp))
    cmake_triplets.clear()
    cmake_triplets.extend(sorted(all_triplets))
    if cmake_triplets:
        target_triplet_combo["values"] = cmake_triplets
        host_triplet_combo["values"] = cmake_triplets
    else:
        target_triplet_combo["values"] = []
        host_triplet_combo["values"] = []
    update_host_triplet_state()


def update_host_triplet_state():
    if cmake_host_same_var.get():
        host_triplet_combo.configure(state="disabled")
        cmake_host_triplet_var.set(cmake_target_triplet_var.get())
    else:
        host_triplet_combo.configure(state="readonly")


def host_same_changed(*args):
    update_host_triplet_state()


def target_triplet_changed(*args):
    if cmake_host_same_var.get():
        cmake_host_triplet_var.set(cmake_target_triplet_var.get())


def select_cmake_project():
    selected = filedialog.askdirectory(title="Select CMake project folder")
    if selected:
        cmake_project_path_var.set(selected)
        detect_cmake_options()


def select_cmake_vcpkg_path():
    selected = filedialog.askdirectory(title="Select vcpkg folder")
    if selected:
        cmake_vcpkg_path_var.set(selected)
        refresh_triplets()


def add_registry_path():
    selected = filedialog.askdirectory(title="Select vcpkg registry folder")
    if not selected:
        return
    if selected not in cmake_registry_paths:
        cmake_registry_paths.append(selected)
        registries_listbox.insert(tk.END, selected)
        refresh_triplets()
        make_cmake_command()


def remove_registry_path():
    selection = registries_listbox.curselection()
    for i in reversed(selection):
        cmake_registry_paths.pop(i)
        registries_listbox.delete(i)
    refresh_triplets()
    make_cmake_command()


def detect_cmake_options():
    project_path = cmake_project_path_var.get().strip()
    for widget in detected_options_frame.winfo_children():
        widget.destroy()
    cmake_detected_options_vars.clear()
    cmake_detected_options_defaults.clear()
    if not project_path:
        return
    p = Path(project_path)
    if not p.exists() or not p.is_dir():
        return

    def strip_quotes(value: str) -> str:
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            return value[1:-1]
        return value

    def cmake_split_tokens(s: str) -> List[str]:
        tokens: List[str] = []
        for t in re.finditer(r"\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s'\"]+))", s):
            token = t.group(1) or t.group(2) or t.group(3) or ""
            tokens.append(token)
        return tokens

    options: set[str] = set()
    option_keys: set[str] = set()
    set_keys: set[str] = set()
    for cmake_file in p.rglob("CMakeLists.txt"):
        try:
            text = cmake_file.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        # option(NAME "help" OFF) with multiline support
        for m in re.finditer(
            r"(?is)\boption\s*\([^)]*\)",
            text,
        ):
            content = m.group(0)
            inner = re.sub(r"(?is)^option\s*\(|\)\s*$", "", content).strip()
            tokens = cmake_split_tokens(inner)
            if not tokens:
                continue
            name = strip_quotes(tokens[0])
            if not name:
                continue
            default = "OFF"
            if len(tokens) >= 3:
                default = strip_quotes(tokens[2])
            options.add(name)
            option_keys.add(name)
            cmake_detected_options_defaults[name] = default

        # set(name value CACHE ...)
        for m in re.finditer(
            r"(?is)\bset\s*\([^)]*\bCACHE\b[^)]*\)",
            text,
        ):
            content = m.group(0)
            inner = re.sub(r"(?is)^set\s*\(|\)\s*$", "", content).strip()
            tokens = cmake_split_tokens(inner)
            if len(tokens) < 2:
                continue
            name = strip_quotes(tokens[0])
            if not name:
                continue
            if name in ["CMAKE_C_FLAGS", "CMAKE_CXX_FLAGS"]:
                continue
            value = strip_quotes(tokens[1])
            options.add(name)
            set_keys.add(name)
            cmake_detected_options_defaults[name] = value

    known = [
        "BUILD_SHARED_LIBS",
        "CMAKE_EXPORT_COMPILE_COMMANDS",
        "BUILD_TESTING",
        "CMAKE_INSTALL_PREFIX",
    ]
    for opt in sorted(options):
        if opt in known:
            continue
        if opt in option_keys:
            default_value = cmake_detected_options_defaults.get(opt, "OFF")
            var = tk.BooleanVar(value=str(default_value).strip().upper() in ("ON", "YES", "TRUE", "1"))
            cmake_detected_options_types[opt] = "option"
        else:
            default_value = cmake_detected_options_defaults.get(opt, "")
            var = tk.StringVar(value=default_value)
            cmake_detected_options_types[opt] = "set"
        cmake_detected_options_vars[opt] = var

    row = 0
    for opt, var in sorted(cmake_detected_options_vars.items()):
        typ = cmake_detected_options_types.get(opt, "set")
        if typ == "option":
            cb = tk.Checkbutton(detected_options_frame, text=opt, variable=var)
            cb.grid(row=row, column=0, columnspan=2, sticky="w", padx=2, pady=2)
        else:
            lbl = tk.Label(detected_options_frame, text=opt + ":")
            lbl.grid(row=row, column=0, sticky="w", padx=2, pady=2)
            ent = tk.Entry(detected_options_frame, textvariable=var, width=45)
            ent.grid(row=row, column=1, sticky="w", padx=2, pady=2)
        row += 1

    detected_options_canvas.configure(scrollregion=detected_options_canvas.bbox("all"))

    for var in cmake_detected_options_vars.values():
        var.trace_add("write", lambda *args: make_cmake_command())

    make_cmake_command()


def make_cmake_command():
    lines: list[str] = []
    cmake_toolchain = cmake_vcpkg_path_var.get().strip()
    if cmake_toolchain:
        lines.append(
            f"-DCMAKE_TOOLCHAIN_FILE={Path(cmake_toolchain) / 'scripts' / 'buildsystems' / 'vcpkg.cmake'}"
        )
    if cmake_registry_paths:
        sel = ";".join(cmake_registry_paths)
        lines.append(f"-DVCPKG_OVERLAY_TRIPLETS={sel}/triplets")
    target = cmake_target_triplet_var.get().strip()
    if target:
        lines.append(f"-DVCPKG_TARGET_TRIPLET={target}")
    if cmake_host_same_var.get():
        if target:
            lines.append(f"-DVCPKG_HOST_TRIPLET={target}")
    else:
        host = cmake_host_triplet_var.get().strip()
        if host:
            lines.append(f"-DVCPKG_HOST_TRIPLET={host}")
    if cmake_build_shared_var.get():
        lines.append("-DBUILD_SHARED_LIBS=ON")
    else:
        lines.append("-DBUILD_SHARED_LIBS=OFF")
    if cmake_export_compile_commands_var.get():
        lines.append("-DCMAKE_EXPORT_COMPILE_COMMANDS=ON")
    else:
        lines.append("-DCMAKE_EXPORT_COMPILE_COMMANDS=OFF")
    if cmake_build_testing_var.get():
        lines.append("-DBUILD_TESTING=ON")
    else:
        lines.append("-DBUILD_TESTING=OFF")
    prefix = cmake_install_prefix_var.get().strip()
    if prefix:
        lines.append(f"-DCMAKE_INSTALL_PREFIX={prefix}")
    for opt, var in sorted(cmake_detected_options_vars.items()):
        typ = cmake_detected_options_types.get(opt, "set")
        if typ == "option":
            if var.get():
                lines.append(f"-D{opt}=ON")
            else:
                lines.append(f"-D{opt}=OFF")
        else:
            val = var.get().strip()
            if val:
                lines.append(f"-D{opt}={val}")
    lines = [line.replace("\\", "/") for line in lines]

    format_type = cmake_output_format_var.get()
    if format_type == "command":
        cmake_command = "cmake " + " \\\n".join(lines)
    elif format_type == "json":
        cmake_command = "\"cmake.configureArgs\":" + json.dumps(lines, indent=2)
    else:
        cmake_command = "cmake " + " \\\n".join(lines)

    cmake_output_text.delete("1.0", tk.END)
    cmake_output_text.insert(tk.END, cmake_command)


def copy_cmake_command():
    root.clipboard_clear()
    root.clipboard_append(cmake_output_text.get("1.0", tk.END).strip())
    messagebox.showinfo("Copied", "Output copied to clipboard")


# CMake tab layout
cmake_row = 0

label = tk.Label(cmake_frame, text="CMake project:")
label.grid(row=cmake_row, column=0, padx=5, pady=5, sticky="w")
entry = tk.Entry(cmake_frame, textvariable=cmake_project_path_var, width=70)
entry.grid(row=cmake_row, column=1, padx=5, pady=5, sticky="we")
btn = tk.Button(cmake_frame, text="Browse...", command=select_cmake_project)
btn.grid(row=cmake_row, column=2, padx=5, pady=5)
cmake_row += 1

label = tk.Label(cmake_frame, text="vcpkg path:")
label.grid(row=cmake_row, column=0, padx=5, pady=5, sticky="w")
entry = tk.Entry(cmake_frame, textvariable=cmake_vcpkg_path_var, width=70)
entry.grid(row=cmake_row, column=1, padx=5, pady=5, sticky="we")
btn = tk.Button(cmake_frame, text="Browse...", command=select_cmake_vcpkg_path)
btn.grid(row=cmake_row, column=2, padx=5, pady=5)
cmake_row += 1

label = tk.Label(cmake_frame, text="vcpkg registries:")
label.grid(row=cmake_row, column=0, padx=5, pady=5, sticky="nw")
registries_listbox = tk.Listbox(cmake_frame, height=4, selectmode=tk.EXTENDED)
registries_listbox.grid(row=cmake_row, column=1, padx=5, pady=5, sticky="we")
btn_add_reg = tk.Button(cmake_frame, text="Add", command=add_registry_path)
btn_add_reg.grid(row=cmake_row, column=2, padx=5, pady=2, sticky="n")
btn_remove_reg = tk.Button(cmake_frame, text="Remove", command=remove_registry_path)
btn_remove_reg.grid(row=cmake_row, column=2, padx=5, pady=30, sticky="n")
cmake_row += 1

label = tk.Label(cmake_frame, text="Target triplet:")
label.grid(row=cmake_row, column=0, padx=5, pady=5, sticky="w")
target_triplet_combo = ttk.Combobox(
    cmake_frame, textvariable=cmake_target_triplet_var, state="readonly"
)
target_triplet_combo.grid(row=cmake_row, column=1, padx=5, pady=5, sticky="we")
cmake_row += 1

host_chk = tk.Checkbutton(
    cmake_frame,
    text="Host triplet equals target",
    variable=cmake_host_same_var,
    command=host_same_changed,
)
host_chk.grid(row=cmake_row, column=0, padx=5, pady=5, sticky="w")

label = tk.Label(cmake_frame, text="Host triplet:")
label.grid(row=cmake_row, column=1, padx=5, pady=5, sticky="w")
host_triplet_combo = ttk.Combobox(
    cmake_frame, textvariable=cmake_host_triplet_var, state="readonly"
)
host_triplet_combo.grid(row=cmake_row, column=1, padx=150, pady=5, sticky="we")
cmake_row += 1

cmake_host_same_var.trace_add("write", host_same_changed)
cmake_target_triplet_var.trace_add("write", target_triplet_changed)

cb1 = tk.Checkbutton(
    cmake_frame, text="BUILD_SHARED_LIBS", variable=cmake_build_shared_var
)
cb1.grid(row=cmake_row, column=0, padx=5, pady=5, sticky="w")
cb2 = tk.Checkbutton(
    cmake_frame,
    text="CMAKE_EXPORT_COMPILE_COMMANDS",
    variable=cmake_export_compile_commands_var,
)
cb2.grid(row=cmake_row, column=1, padx=5, pady=5, sticky="w")
cmake_row += 1

cb3 = tk.Checkbutton(
    cmake_frame, text="BUILD_TESTING", variable=cmake_build_testing_var
)
cb3.grid(row=cmake_row, column=0, padx=5, pady=5, sticky="w")
label = tk.Label(cmake_frame, text="CMAKE_INSTALL_PREFIX:")
label.grid(row=cmake_row, column=1, padx=5, pady=5, sticky="w")
ent = tk.Entry(cmake_frame, textvariable=cmake_install_prefix_var, width=40)
ent.grid(row=cmake_row, column=1, padx=160, pady=5, sticky="we")
cmake_row += 1

# Detected options container
label = tk.Label(cmake_frame, text="Detected CMake options:")
label.grid(row=cmake_row, column=0, padx=5, pady=5, sticky="nw")
detected_options_canvas = tk.Canvas(cmake_frame, height=350)
detected_options_scrollbar = ttk.Scrollbar(
    cmake_frame, orient="vertical", command=detected_options_canvas.yview
)
detected_options_canvas.configure(yscrollcommand=detected_options_scrollbar.set)
detected_options_canvas.grid(row=cmake_row, column=1, padx=5, pady=5, sticky="nsew")
detected_options_scrollbar.grid(row=cmake_row, column=2, sticky="ns")
detected_options_frame = ttk.Frame(detected_options_canvas)
detected_options_canvas.create_window(
    (0, 0), window=detected_options_frame, anchor="nw"
)
cmake_row += 1

# Output format
label = tk.Label(cmake_frame, text="Output format:")
label.grid(row=cmake_row, column=0, padx=5, pady=5, sticky="w")
rb_command = tk.Radiobutton(
    cmake_frame, text="Command Line", variable=cmake_output_format_var, value="command"
)
rb_command.grid(row=cmake_row, column=1, padx=5, pady=5, sticky="w")
rb_json = tk.Radiobutton(
    cmake_frame,
    text="VSCode settings.json",
    variable=cmake_output_format_var,
    value="json",
)
rb_json.grid(row=cmake_row, column=2, padx=5, pady=5, sticky="w")
cmake_row += 1

btn_copy = tk.Button(cmake_frame, text="Copy output", command=copy_cmake_command)
btn_copy.grid(row=cmake_row, column=0, padx=5, pady=10, sticky="w")
cmake_row += 1

cmake_output_text = tk.Text(cmake_frame, height=8, width=100)
cmake_output_text.grid(
    row=cmake_row, column=0, columnspan=3, padx=5, pady=5, sticky="nsew"
)

cmake_frame.grid_rowconfigure(cmake_row, weight=1)
cmake_frame.grid_columnconfigure(1, weight=1)

cmake_project_path_var.trace_add("write", lambda *args: make_cmake_command())
cmake_vcpkg_path_var.trace_add("write", lambda *args: make_cmake_command())
cmake_target_triplet_var.trace_add("write", lambda *args: make_cmake_command())
cmake_host_triplet_var.trace_add("write", lambda *args: make_cmake_command())
cmake_host_same_var.trace_add("write", lambda *args: make_cmake_command())
cmake_build_shared_var.trace_add("write", lambda *args: make_cmake_command())
cmake_export_compile_commands_var.trace_add("write", lambda *args: make_cmake_command())
cmake_build_testing_var.trace_add("write", lambda *args: make_cmake_command())
cmake_install_prefix_var.trace_add("write", lambda *args: make_cmake_command())
cmake_output_format_var.trace_add("write", lambda *args: make_cmake_command())

make_cmake_command()

# Table
columns = ("Key", "Value 1", "Value 2")
tree = ttk.Treeview(package_frame, columns=columns, show="headings")
tree.heading("Key", text="Key")
tree.heading("Value 1", text="Value 1")
tree.heading("Value 2", text="Value 2")
tree.grid(row=3, column=0, columnspan=4, padx=5, pady=5, sticky="nsew")

scrollbar = ttk.Scrollbar(package_frame, orient="vertical", command=tree.yview)
scrollbar.grid(row=3, column=4, sticky="ns")
tree.configure(yscrollcommand=scrollbar.set)

package_frame.grid_rowconfigure(3, weight=1)
package_frame.grid_columnconfigure(1, weight=1)


def update_table(var: str, index: str, mode: str):
    pkg, date1_str, date2_str, _ = history.current()

    tree.delete(*tree.get_children())

    if not pkg or not date1_str:
        return

    dates = sorted(vcpkg_archives.database[pkg].keys())

    date1_idx = dates.index(date1_str)
    date1 = dates[date1_idx]
    dict1 = vars(vcpkg_archives.database[pkg][date1])

    if date2_str:
        date2_idx = dates.index(date2_str)
        date2 = dates[date2_idx]
        dict2 = vars(vcpkg_archives.database[pkg][date2])

        all_keys = set(dict1.keys()) | set(dict2.keys())
        for key in sorted(all_keys):
            val1 = dict1.get(key, "")
            val2 = dict2.get(key, "")
            if val1 != val2:
                tree.insert("", "end", values=(key, val1, val2))
    else:
        for key, val in sorted(dict1.items()):
            tree.insert("", "end", values=(key, val, ""))


history.trace_add(update_table)


def on_double_click(event: tk.Event):
    item = tree.selection()
    if not item:
        return

    values = tree.item(item[0], "values")
    if not values:
        return

    key = values[0]
    sha1 = values[1]
    sha2 = values[2]

    # Check if key is a package name in result
    if key not in vcpkg_archives.database:
        return

    # Find dates matching sha1 and sha2
    dates = sorted(vcpkg_archives.database[key].keys())
    date1 = None
    date2 = None

    for date in dates:
        abi_dict = vars(vcpkg_archives.database[key][date])
        # Assuming sha is stored in a specific key, adjust as needed
        for _, abi_value in abi_dict.items():
            if sha1 and abi_value == sha1:
                date1 = date
            if sha2 and abi_value == sha2:
                date2 = date

    if date1 and date2:
        history.disabled()
        package_combo_var.set(key)

        if date1:
            date1_combo_var.set(date1)
        if date2:
            date2_combo_var.set(date2)

        history.enabled()
        history.save_state(
            HistoryStruct(
                package=package_combo_var.get(),
                date1=date1_combo_var.get(),
                date2=date2_combo_var.get(),
                same_triplet=data2_same_triplet_var.get(),
            )
        )


tree.bind("<Double-1>", on_double_click)

root.mainloop()
