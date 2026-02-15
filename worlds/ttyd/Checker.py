import json
import os
import re
import time

DOORS_FILE = "files/zones.json"
REGIONS_FILE = "files/regions.json"
DOLPHIN_LOG = os.path.expanduser("~/Documents/Dolphin Emulator/Logs/dolphin.log")

MAP_RE = re.compile(r"map=([^\s]+)\s+bero=([^\s]+)")


def load_json(path):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


def tail_file(path):
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        f.seek(0, os.SEEK_END)
        while True:
            line = f.readline()
            if not line:
                time.sleep(0.2)
                continue
            yield line


def prompt_with_default(label, default):
    if default:
        value = input(f"{label} [{default}]: ").strip()
        return value if value else default
    return input(f"{label}: ").strip()


def prompt_rules():
    choice = input("Rule type (has / function / can_reach / or / and / null): ").strip()

    if not choice or choice == "null":
        return None

    if choice in ("has", "function", "can_reach", "can_reach_region", "can_reach_entrance"):
        return {choice: input(f"{choice}: ").strip()}

    if choice in ("or", "and"):
        rules = []
        print(f"Nested rules for '{choice}' (empty line to finish)")
        while True:
            sub = prompt_rules()
            if sub is None:
                break
            rules.append(sub)
        return {choice: rules}

    print("Invalid rule type.")
    return prompt_rules()


def main():
    doors = load_json(DOORS_FILE)
    regions = load_json(REGIONS_FILE)

    known_pairs = {(d["map"], d["bero"]) for d in doors}
    known_names = {d["name"] for d in doors}
    region_lookup = {r["tag"]: r for r in regions}

    last_name = None
    last_target = None
    last_region_tag = None
    last_region_chapter = None

    print("Watching Dolphin OSReport log…")

    for line in tail_file(DOLPHIN_LOG):
        if "[MAP LOADING]" not in line:
            continue

        match = MAP_RE.search(line)
        if not match:
            continue

        map_name, bero = match.groups()

        if (map_name, bero) in known_pairs:
            continue

        print(f"\nNew map detected: map={map_name}, bero={bero}")

        # Name defaults to last target
        name = prompt_with_default("Name", last_target)

        # Target defaults to last name
        while True:
            target = prompt_with_default("Target", last_name)

            if target == "One Way":
                break

            if target in known_names:
                break

            confirm = input(
                f"Target '{target}' does not match an existing name. "
                "Press Enter to confirm, or type a new target: "
            ).strip()

            if confirm == "":
                break

            target = confirm

        entry = {
            "name": name,
            "map": map_name,
            "bero": bero,
            "target": target,
        }

        if target == "One Way":
            entry["src_region"] = input("Source region: ").strip()

        entry["rules"] = prompt_rules()

        # Region defaults to last entry's region
        region_tag = prompt_with_default("Region tag", last_region_tag)
        entry["region"] = region_tag

        if region_tag not in region_lookup:
            print("New region detected.")
            region_name = input("Region name: ").strip()

            chapter = prompt_with_default(
                "Chapter",
                last_region_chapter
            )

            region_data = {
                "name": region_name,
                "tag": region_tag,
                "chapter": chapter
            }

            regions.append(region_data)
            region_lookup[region_tag] = region_data
            save_json(REGIONS_FILE, regions)

            last_region_chapter = chapter

        doors.append(entry)
        save_json(DOORS_FILE, doors)

        # Update state
        known_pairs.add((map_name, bero))
        known_names.add(name)

        last_name = name
        last_target = target
        last_region_tag = region_tag

        print("Entry saved.")


if __name__ == "__main__":
    main()
