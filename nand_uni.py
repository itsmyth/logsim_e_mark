#!/usr/bin/env python3
import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

# Hardwired path to logisim-evolution.jar
LOGISIM_JAR_PATH = "logisim-evolution.jar"

# Execution timeout threshold in seconds
TIMEOUT_SECONDS = 30


def resolve_project_path(prompt_text):
    """Prompts the user for the .circ file path and validates existence."""
    while True:
        path_input = input(prompt_text).strip().strip("'\"")

        if not path_input:
            print("Path cannot be empty. Please try again.\n")
            continue

        resolved_path = os.path.abspath(path_input)

        if not os.path.exists(resolved_path):
            print(f"Error: File not found at '{resolved_path}'. Please check the path.\n")
            continue

        return resolved_path


def get_circuit_details(circ_file):
    """Parses .circ XML for circuits, handling both modern 'type' and legacy 'output' attributes."""
    try:
        tree = ET.parse(circ_file)
        root = tree.getroot()
        circuits = []

        for circuit in root.findall("circuit"):
            name = circuit.get("name")
            if not name:
                continue

            pins = circuit.findall(".//comp[@name='Pin']")
            inputs = 0
            outputs = 0

            for pin in pins:
                is_output = False
                for attr in pin.findall("a"):
                    attr_name = attr.get("name")
                    attr_val = str(attr.get("val")).lower()

                    if attr_name == "type" and attr_val == "output":
                        is_output = True
                        break
                    elif attr_name == "output" and attr_val == "true":
                        is_output = True
                        break

                if is_output:
                    outputs += 1
                else:
                    inputs += 1

            circuits.append({
                "name": name,
                "inputs": inputs,
                "outputs": outputs
            })

        return circuits
    except ET.ParseError:
        print("Error: Could not parse XML from the specified file.")
        return []


def parse_selection(user_input, total_circuits):
    """Parses selections like '1, 3, 5', '1-4', or combinations into zero-based indices."""
    selected_indices = set()
    parts = user_input.replace(" ", "").split(",")

    for part in parts:
        if not part:
            continue
        if "-" in part:
            bounds = part.split("-")
            if len(bounds) == 2 and bounds[0].isdigit() and bounds[1].isdigit():
                start, end = int(bounds[0]), int(bounds[1])
                if 1 <= start <= end <= total_circuits:
                    selected_indices.update(range(start - 1, end))
                else:
                    return None
            else:
                return None
        elif part.isdigit():
            val = int(part)
            if 1 <= val <= total_circuits:
                selected_indices.add(val - 1)
            else:
                return None
        else:
            return None

    return sorted(list(selected_indices))


def prompt_circuit_selection(total_circuits):
    """Prompts user to enter circuit numbers, ranges, or press Enter for all."""
    while True:
        prompt_str = (
            f"Select circuits to analyze (e.g., '1, 3, 5', '1-4', or press Enter for ALL): "
        )
        user_input = input(prompt_str).strip()

        if not user_input:
            return list(range(total_circuits))

        selected = parse_selection(user_input, total_circuits)
        if selected:
            return selected

        print(f"Invalid selection. Please enter valid numbers/ranges between 1 and {total_circuits}.\n")


def create_temp_circ_with_main(original_circ_file, target_circuit_name):
    """Creates a temporary copy of the .circ file with the target circuit as top-level main."""
    tree = ET.parse(original_circ_file)
    root = tree.getroot()

    main_elem = root.find("main")
    if main_elem is not None:
        main_elem.set("name", target_circuit_name)
    else:
        new_main = ET.Element("main", name=target_circuit_name)
        root.insert(0, new_main)

    temp_file = tempfile.NamedTemporaryFile(suffix=".circ", delete=False)
    temp_path = temp_file.name
    temp_file.close()

    tree.write(temp_path, encoding="utf-8", xml_declaration=True)
    return temp_path


def generate_truth_table_for_circuit(circ_file, circuit_name, jar_path):
    """Generates the truth table with a 30-second execution timeout."""
    temp_circ_path = None
    try:
        temp_circ_path = create_temp_circ_with_main(circ_file, circuit_name)

        cmd = [
            "java", "-jar", jar_path,
            "-tty", "table",
            temp_circ_path
        ]

        # Enforce 30-second timeout
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            timeout=TIMEOUT_SECONDS
        )
        return result.stdout

    except subprocess.TimeoutExpired:
        print(f"\n[ERROR] Truth table generation for '{circuit_name}' timed out after {TIMEOUT_SECONDS} seconds.")
        print("Terminating script execution.")
        if temp_circ_path and os.path.exists(temp_circ_path):
            os.remove(temp_circ_path)
        sys.exit(1)

    except subprocess.CalledProcessError as e:
        return f"Error executing circuit '{circuit_name}': {e.stderr.strip()}"
    except FileNotFoundError:
        return f"Error: Java runtime or logisim JAR not found at '{jar_path}'."
    finally:
        if temp_circ_path and os.path.exists(temp_circ_path):
            os.remove(temp_circ_path)


def main():
    print("=== Logisim-Evolution Truth Table Generator ===\n")

    jar_path = os.path.abspath(LOGISIM_JAR_PATH)
    if not os.path.exists(jar_path):
        print(f"Error: Hardwired logisim JAR file not found at: {jar_path}")
        print("Please check LOGISIM_JAR_PATH at the top of the script.")
        return

    project_file = resolve_project_path("Enter path to your project file (.circ): ")

    circuits = get_circuit_details(project_file)

    if not circuits:
        print("No valid circuits found in the project file.")
        return

    total_found = len(circuits)
    print(f"\nFound {total_found} circuit(s) in project:\n")
    for idx, c in enumerate(circuits, 1):
        print(f" {idx:2d}. {c['name']:<30} [{c['inputs']} Input(s), {c['outputs']} Output(s)]")
    print()

    selected_indices = prompt_circuit_selection(total_found)
    selected_circuits = [circuits[i] for i in selected_indices]

    print(f"\nAnalyzing {len(selected_circuits)} selected circuit(s)...\n")

    for c in selected_circuits:
        c_name = c["name"]
        print("=" * 55)
        print(f" Truth Table: {c_name}")
        print("=" * 55)

        table = generate_truth_table_for_circuit(project_file, c_name, jar_path)
        print(table if table.strip() else "[No table generated or circuit has 0 inputs/outputs]")


if __name__ == "__main__":
    main()
