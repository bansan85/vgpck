from pathlib import Path
import sys
from zipfile import ZipFile
from datetime import datetime
from typing import Optional, Dict, List
import tkinter as tk
from tkinter import ttk
import os
from typing import NamedTuple
from types import SimpleNamespace
from collections.abc import Callable

binary_cache = os.getenv("VCPKG_DEFAULT_BINARY_CACHE")
binary_cache = R"\\wsl$\Ubuntu-24.04\home\vlegarrec\.cache\vcpkg\archives"
if binary_cache is None:  # type: ignore
    print("VCPKG_DEFAULT_BINARY_CACHE environment variable is not set.")
    sys.exit(0)


class VcpkgArchives:
    def __init__(self, path: str):
        self.path = path
        self.read_archives()

    def read_archives(self):
        zip_files = list(Path(self.path).rglob("*.zip"))
        database: Dict[str, Dict[datetime, SimpleNamespace]] = {}
        for f in zip_files:
            with ZipFile(f, "r") as zf:
                info = zf.getinfo("BUILD_INFO")
                dt = datetime(*info.date_time)

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
        return [d.strftime("%Y-%m-%d %H:%M:%S") for d in dates]


class HistoryStruct(NamedTuple):
    package: str
    date1: str
    date2: str


vcpkg_archives = VcpkgArchives(binary_cache)

root = tk.Tk()


class History:
    def __init__(self):
        self.stack: List[HistoryStruct] = [
            HistoryStruct(package="", date1="", date2="")
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

    def can_increment(self):
        return self.history_index.get() >= self.length() - 1

    def can_decrement(self):
        return self.history_index.get() < 1

    def trace_add(self, callback: Callable[[str, str, str], object]):
        self.history_index.trace_add("write", callback=callback)


history = History()


root.title("Package Comparison")
root.geometry("800x600")


def trace_prev_button_state(var: str, index: str, mode: str):
    prev_button.configure(state="normal" if history.can_decrement() < 1 else "disabled")


def trace_next_button_state(var: str, index: str, mode: str):
    next_button.configure(state="normal" if not history.can_increment() else "disabled")


prev_button = tk.Button(root, text="< Previous", command=lambda: history.decrement())
prev_button.grid(row=0, column=2, padx=5, pady=5)
prev_button.configure(state="disabled")
history.history_index.trace_add(
    "write",
    callback=trace_prev_button_state,
)
next_button = tk.Button(root, text="Next >", command=lambda: history.increment())
next_button.grid(row=0, column=3, padx=5, pady=5)
next_button.configure(state="disabled")
history.trace_add(trace_next_button_state)

tk.Label(root, text="Package:").grid(row=0, column=0, padx=5, pady=5)
package_combo_var = tk.StringVar()
package_combo = ttk.Combobox(
    root,
    values=vcpkg_archives.sorted_packages(),
    state="readonly",
    textvariable=package_combo_var,
)
package_combo.grid(row=0, column=1, padx=5, pady=5)


def trace_package_combo(var: str, index: str, mode: str):
    pkg = package_combo_var.get()
    if pkg and pkg in vcpkg_archives.database:
        date1_combo["values"] = vcpkg_archives.get_dates(pkg)
    history.save_state(HistoryStruct(package=pkg, date1="", date2=""))


def trace_package_combo_form_history_index(var: str, index: str, mode: str):
    package_combo_var.set(history.current().package)


package_combo_var.trace_add(mode="write", callback=trace_package_combo)
history.trace_add(trace_package_combo_form_history_index)

tk.Label(root, text="Date 1:").grid(row=1, column=0, padx=5, pady=5)
date1_combo_var = tk.StringVar()
date1_combo = ttk.Combobox(root, state="readonly", textvariable=date1_combo_var)
date1_combo.grid(row=1, column=1, padx=5, pady=5)


def trace_date1_combo(var: str, index: str, mode: str):
    history.save_state(
        HistoryStruct(
            package=package_combo_var.get(), date1=date1_combo_var.get(), date2=""
        )
    )
    # if var_data2_same_tripler.get() and date1_combo.get() != "":
    #     date_strs = [
    #         d.strftime("%Y-%m-%d %H:%M:%S")
    #         for d in dates
    #         if database[pkg][
    #             datetime.strptime(date1_combo.get(), "%Y-%m-%d %H:%M:%S")
    #         ]["triplet"]
    #         == database[pkg][d]["triplet"]
    #     ]
    # else:
    date_strs = list(date1_combo["values"])
    date_strs.insert(0, "")
    date2_combo["values"] = date_strs


def trace_date1_combo_form_history_index(var: str, index: str, mode: str):
    date1_combo_var.set(history.current().date1)


date1_combo_var.trace_add(mode="write", callback=trace_date1_combo)
history.trace_add(trace_date1_combo_form_history_index)


tk.Label(root, text="Date 2:").grid(row=2, column=0, padx=5, pady=5)
date2_combo_var = tk.StringVar()
date2_combo = ttk.Combobox(root, state="readonly", textvariable=date2_combo_var)
date2_combo.grid(row=2, column=1, padx=5, pady=5)


def trace_date2_combo(var: str, index: str, mode: str):
    history.save_state(
        HistoryStruct(
            package=package_combo_var.get(),
            date1=date1_combo_var.get(),
            date2=date2_combo_var.get(),
        )
    )


def trace_date2_combo_form_history_index(var: str, index: str, mode: str):
    date2_combo_var.set(history.current().date2)


date2_combo_var.trace_add(mode="write", callback=trace_date2_combo)
history.trace_add(trace_date2_combo_form_history_index)


# var_data2_same_tripler = tk.BooleanVar()
# data2_same_tripler = ttk.Checkbutton(
#     root, text="Same triplet", variable=var_data2_same_tripler
# )
# data2_same_tripler.grid(row=2, column=2, padx=5, pady=5)

# # Table
# columns = ("Key", "Value 1", "Value 2")
# tree = ttk.Treeview(root, columns=columns, show="headings")
# tree.heading("Key", text="Key")
# tree.heading("Value 1", text="Value 1")
# tree.heading("Value 2", text="Value 2")
# tree.grid(row=3, column=0, columnspan=4, padx=5, pady=5, sticky="nsew")

# scrollbar = ttk.Scrollbar(root, orient="vertical", command=tree.yview)
# scrollbar.grid(row=3, column=4, sticky="ns")
# tree.configure(yscrollcommand=scrollbar.set)

# root.grid_rowconfigure(3, weight=1)
# root.grid_columnconfigure(1, weight=1)


# def update_nav_buttons():
#     prev_button["state"] = "normal" if history_index > 0 else "disabled"
#     next_button["state"] = "normal" if history_index < len(history) - 1 else "disabled"


# def save_state():
#     global history_index

#     state = {
#         "package": package_combo.get(),
#         "date1": date1_combo.get(),
#         "date2": date2_combo.get(),
#     }

#     history[history_index + 1 :] = []

#     history.append(state)
#     history_index = len(history) - 1
#     update_nav_buttons()


def navigate(direction: int):
    global skip_save_state
    history.increment()
    # global history_index

    # new_index: int = history_index + direction
    # if 0 <= new_index < len(history):
    #     history_index = new_index
    #     state = history[history_index]

    #     package_combo.set(state["package"])
    #     update_dates(tk.Event(), skip_save=True)
    #     date1_combo.set(state["date1"])
    #     date2_combo.set(state["date2"])
    #     update_table(tk.Event(), skip_save=True)

    #     update_nav_buttons()


# def update_dates(event: tk.Event, skip_save: bool = False) -> None:
#     if not skip_save:
#         save_state()

#     pkg = package_combo.get()
#     if pkg and pkg in database:
#         dates = sorted(database[pkg].keys())
#         date_strs = [d.strftime("%Y-%m-%d %H:%M:%S") for d in dates]
#         date1_combo["values"] = date_strs
#         date_strs.insert(0, "")
#         date2_combo["values"] = date_strs
#         update_date2(event, skip_save)


# def update_date2(event: tk.Event, skip_save: bool = False) -> None:
#     pkg = package_combo.get()
#     if pkg and pkg in database:
#         dates = sorted(database[pkg].keys())

#         if var_data2_same_tripler.get() and date1_combo.get() != "":
#             date_strs = [
#                 d.strftime("%Y-%m-%d %H:%M:%S")
#                 for d in dates
#                 if database[pkg][
#                     datetime.strptime(date1_combo.get(), "%Y-%m-%d %H:%M:%S")
#                 ]["triplet"]
#                 == database[pkg][d]["triplet"]
#             ]
#         else:
#             date_strs = [d.strftime("%Y-%m-%d %H:%M:%S") for d in dates]
#         date_strs.insert(0, "")
#         date2_str = date2_combo.get()
#         date2_combo["values"] = date_strs
#         if date2_str in date_strs:
#             date2_combo.set(date2_str)
#         else:
#             date2_combo.set("")
#         tree.delete(*tree.get_children())

#     update_table(event, skip_save)


# def update_table(event: tk.Event, skip_save: bool = False) -> None:
#     if not skip_save:
#         save_state()

#     pkg = package_combo.get()
#     date1_str = date1_combo.get()
#     date2_str = date2_combo.get()

#     tree.delete(*tree.get_children())

#     if not pkg or not date1_str:
#         return

#     dates = sorted(database[pkg].keys())
#     date_strs = [d.strftime("%Y-%m-%d %H:%M:%S") for d in dates]

#     date1_idx = date_strs.index(date1_str)
#     date1 = dates[date1_idx]
#     dict1 = database[pkg][date1]

#     if date2_str:
#         date2_idx = date_strs.index(date2_str)
#         date2 = dates[date2_idx]
#         dict2 = database[pkg][date2]

#         all_keys = set(dict1.keys()) | set(dict2.keys())
#         for key in sorted(all_keys):
#             val1 = dict1.get(key, "")
#             val2 = dict2.get(key, "")
#             if val1 != val2:
#                 tree.insert("", "end", values=(key, val1, val2))
#     else:
#         for key, val in sorted(dict1.items()):
#             tree.insert("", "end", values=(key, val, ""))


# def on_double_click(event: tk.Event):
#     item = tree.selection()
#     if not item:
#         return

#     values = tree.item(item[0], "values")
#     if not values:
#         return

#     key = values[0]
#     sha1 = values[1]
#     sha2 = values[2]

#     # Check if key is a package name in result
#     if key not in database:
#         return

#     # Find dates matching sha1 and sha2
#     dates = sorted(database[key].keys())
#     date1 = None
#     date2 = None

#     for date in dates:
#         abi_dict = database[key][date]
#         # Assuming sha is stored in a specific key, adjust as needed
#         for _, abi_value in abi_dict.items():
#             if sha1 and abi_value == sha1:
#                 date1 = date
#             if sha2 and abi_value == sha2:
#                 date2 = date

#     if date1 and date2:
#         package_combo.set(key)
#         update_dates(event, skip_save=True)

#         if date1:
#             date1_combo.set(date1.strftime("%Y-%m-%d %H:%M:%S"))
#         if date2:
#             date2_combo.set(date2.strftime("%Y-%m-%d %H:%M:%S"))

#         update_table(event, skip_save=True)
#         save_state()


# package_combo.bind("<<ComboboxSelected>>", update_dates)
# date1_combo.bind("<<ComboboxSelected>>", update_date2)
# date2_combo.bind("<<ComboboxSelected>>", update_table)
# tree.bind("<Double-1>", on_double_click)
# var_data2_same_tripler.trace_add("write", lambda *args: update_date2(None))

# update_nav_buttons()

root.mainloop()
