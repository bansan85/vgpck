from pathlib import Path
from zipfile import ZipFile
from datetime import datetime
from typing import Optional, Dict
import tkinter as tk
from tkinter import ttk

# Method 1: Using pathlib (recommended)
zip_files = list(Path('H:/cache/vcpkg').rglob('*.zip'))
database : Dict[str, Dict[datetime, Dict[str, str]]] = {}
for f in zip_files:
    with ZipFile(f, 'r') as zf:
        info = zf.getinfo('BUILD_INFO')
        dt = datetime(*info.date_time)
        
        content = zf.read('CONTROL').decode('utf-8')
        
        package_name: Optional[str] = None
        abi : Optional[str] = None
        for line in content.split('\n'):
            if line.startswith('Package:'):
                package_name = line.split(':', 1)[1].strip()
            if line.startswith('Abi:'):
                abi = line.split(':', 1)[1].strip()

        assert package_name is not None
        assert abi is not None
            
        # Read vcpkg_abi_info.txt
        abi_path = f'share/{package_name}/vcpkg_abi_info.txt'
        abi_content = zf.read(abi_path).decode('utf-8')

        # Parse to dict
        abi_dict = {}
        abi_dict["abi"] = abi
        for line in abi_content.split('\n'):
            if line.strip():
                key, value = line.split(None, 1)
                abi_dict[key] = value

        if package_name not in database:
            database[package_name] = {}
        database[package_name][dt] = abi_dict

root = tk.Tk()
root.title("Package Comparison")
root.geometry("800x600")

# Package selection
tk.Label(root, text="Package:").grid(row=0, column=0, padx=5, pady=5)
sorted_packages = list(database.keys())
sorted_packages.sort()
package_combo = ttk.Combobox(root, values=sorted_packages, state="readonly")
package_combo.grid(row=0, column=1, padx=5, pady=5)

# Date selections
tk.Label(root, text="Date 1:").grid(row=1, column=0, padx=5, pady=5)
date1_combo = ttk.Combobox(root, state="readonly")
date1_combo.grid(row=1, column=1, padx=5, pady=5)

tk.Label(root, text="Date 2:").grid(row=2, column=0, padx=5, pady=5)
date2_combo = ttk.Combobox(root, state="readonly")
date2_combo.grid(row=2, column=1, padx=5, pady=5)

# Table
columns = ("Key", "Value 1", "Value 2")
tree = ttk.Treeview(root, columns=columns, show="headings")
tree.heading("Key", text="Key")
tree.heading("Value 1", text="Value 1")
tree.heading("Value 2", text="Value 2")
tree.grid(row=3, column=0, columnspan=2, padx=5, pady=5, sticky="nsew")

scrollbar = ttk.Scrollbar(root, orient="vertical", command=tree.yview)
scrollbar.grid(row=3, column=2, sticky="ns")
tree.configure(yscrollcommand=scrollbar.set)

root.grid_rowconfigure(3, weight=1)
root.grid_columnconfigure(1, weight=1)

def update_dates(event: tk.Event) -> None:
    pkg = package_combo.get()
    if pkg and pkg in database:
        dates = sorted(database[pkg].keys())
        date_strs = [d.strftime("%Y-%m-%d %H:%M:%S") for d in dates]
        date1_combo['values'] = date_strs
        date_strs.insert(0, '')
        date2_combo['values'] = date_strs
        date1_combo.set('')
        date2_combo.set('')
        tree.delete(*tree.get_children())

def update_table(event: tk.Event) -> None:
    pkg = package_combo.get()
    date1_str = date1_combo.get()
    date2_str = date2_combo.get()
    
    tree.delete(*tree.get_children())
    
    if not pkg or not date1_str:
        return
    
    dates = sorted(database[pkg].keys())
    date_strs = [d.strftime("%Y-%m-%d %H:%M:%S") for d in dates]
    
    date1_idx = date_strs.index(date1_str)
    date1 = dates[date1_idx]
    dict1 = database[pkg][date1]
    
    if date2_str:
        date2_idx = date_strs.index(date2_str)
        date2 = dates[date2_idx]
        dict2 = database[pkg][date2]
        
        all_keys = set(dict1.keys()) | set(dict2.keys())
        for key in sorted(all_keys):
            val1 = dict1.get(key, "")
            val2 = dict2.get(key, "")
            if val1 != val2:
                tree.insert("", "end", values=(key, val1, val2))
    else:
        for key, val in sorted(dict1.items()):
            tree.insert("", "end", values=(key, val, ""))

package_combo.bind("<<ComboboxSelected>>", update_dates)
date1_combo.bind("<<ComboboxSelected>>", update_table)
date2_combo.bind("<<ComboboxSelected>>", update_table)

root.mainloop()