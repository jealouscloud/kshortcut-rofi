# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///

import os
import shutil
import subprocess
from pathlib import Path
from typing import NamedTuple, Optional


class Shortcut(NamedTuple):
    component: Optional[str]
    pretty_component: Optional[str]
    command: str
    shortcuts: list[str]
    pretty_command: Optional[str]


def send_kglobalaccel_dbus(component, function, *args):
    cmd = [
        "qdbus",
        "org.kde.kglobalaccel",
        f"/component/{component}",
        function,
        *args,
    ]
    return subprocess.run(cmd, check=True, capture_output=True)


def read_file():
    config_dir = Path(
        os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    )
    config_file = config_dir / "kglobalshortcutsrc"
    if not config_file.exists():
        print(f"Configuration file not found: {config_file}")
        exit(1)
        return None

    lines = config_file.read_text().splitlines()
    section = None
    result = []
    section_names = {}
    for i, line in enumerate(lines):
        if line.strip() == "":
            continue

        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip()
            section_names[section] = section
            continue
        kv = line.split("=", 1)
        if len(kv) != 2:
            print(f"Invalid line {i + 1} in config file: {line}")
            exit(1)
        command = kv[0].strip()
        if command.startswith("_"):
            if command == "_k_friendly_name":
                # this is the pretty name for the section
                section_names[section] = kv[1].strip()
                continue
            if command != "_launch":
                print(f"Unknown command {command} in config file: {line}")
                continue
        value = kv[1].strip()
        is_desktop_file = section and section.startswith("services")
        if is_desktop_file and section:
            # desktop launchers.
            assert "[" in section, (
                "Service launchers should look like this. "
                "[services][net.local.flameshot-2.desktop]"
            )
            entries = value.split(r"\t")
            shortcuts = entries
            pretty_name = command
        else:
            entries = value.split(",")
            shortcut_defs = entries[:-1]  # all but the first/last entry

            shortcuts = []
            for shortcut in shortcut_defs:
                if r"\t" in shortcut:
                    shortcut = shortcut.replace(r"\t", "\t")
                shortcuts.extend(
                    [x for x in shortcut.split("\t") if x]
                )  # split by tab
            pretty_name = entries[-1].strip()
        assert shortcuts, (
            "Shortcuts list should not be empty. "
            "Even no assignment should be 'none'"
        )
        result.append(
            Shortcut(
                component=section,
                pretty_component=None,
                command=command,
                shortcuts=shortcuts,
                pretty_command=pretty_name,
            )
        )

    real_result: list[Shortcut] = []
    for i, shortcut in enumerate(result):
        section_name = shortcut.component
        pretty_command = shortcut.pretty_command
        if section_name.startswith("services"):
            # desktop launchers.
            desktop_file = section_name.split("[")[1]
            section_name = desktop_file.replace(".", "_").replace("-", "_")
            try:
                friendlyName = send_kglobalaccel_dbus(
                    section_name, "org.kde.kglobalaccel.Component.friendlyName"
                )
                pretty_command = friendlyName.stdout.decode("utf-8").strip()

            except subprocess.CalledProcessError:
                pass
            section_names[section_name] = desktop_file

        cleaned_shortcuts = list(set(shortcut.shortcuts))
        if len(cleaned_shortcuts) > 1:
            cleaned_shortcuts = [x for x in cleaned_shortcuts if x != "none"]

        real_result.append(
            Shortcut(
                component=section_name,
                pretty_component=section_names.get(section_name, section_name),
                command=shortcut.command,
                shortcuts=cleaned_shortcuts,
                pretty_command=pretty_command,
            )
        )
        # this is the pretty name for the section
    return real_result


def main() -> None:
    if not shutil.which("rofi"):
        print("Rofi is not in $PATH. Please install it to use this script.")
        exit(1)
    if not shutil.which("qdbus"):
        print("qdbus is not in $PATH. Please install qdbus.")
        exit(1)

    config = read_file()
    short_map = {}
    for shortcut in config:
        short_map[
            f"{shortcut.pretty_component}::{shortcut.pretty_command} ({', '.join(shortcut.shortcuts)})".strip()
        ] = shortcut

    result = subprocess.run(
        ["rofi", "-dmenu", "-i", "-p", "KGlobalShortcuts"],
        input="\n".join(short_map.keys()).encode("utf-8"),
        capture_output=True,
    )
    if result.returncode == 0:
        selected = result.stdout.decode("utf-8").strip()
        if not selected:
            print("No selection made.")
            exit(0)
        selected_shortcut = short_map[selected]
        send_kglobalaccel_dbus(
            selected_shortcut.component,
            "org.kde.kglobalaccel.Component.invokeShortcut",
            selected_shortcut.command,
        )


if __name__ == "__main__":
    main()
