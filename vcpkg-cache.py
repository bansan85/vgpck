from pathlib import Path
import sys
from zipfile import ZipFile
from datetime import datetime
from typing import Optional, Dict, List
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


prev_button = tk.Button(package_frame, text="< Previous", command=lambda: history.decrement())
prev_button.grid(row=0, column=2, padx=5, pady=5)
prev_button.configure(state="disabled")
history.trace_add(trace_prev_button_state)
next_button = tk.Button(package_frame, text="Next >", command=lambda: history.increment())
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
        date1_str=""
    if (
        not pkg in vcpkg_archives.database
        or not date2_str in vcpkg_archives.database[pkg]
    ):
        date2_combo_var.set("")
        date2_str=""
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
date1_combo = ttk.Combobox(package_frame, state="readonly", textvariable=date1_combo_var)
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
        date2_str=""
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
            date2_str=""

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
date2_combo = ttk.Combobox(package_frame, state="readonly", textvariable=date2_combo_var)
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

    choices : list[str] = []
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
