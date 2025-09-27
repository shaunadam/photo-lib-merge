import json
import subprocess
import sys


def print_exif_exiftool(file_path):
    """
    Calls exiftool with JSON output and prints key/value pairs
    for all metadata found in 'file_path'.
    """
    # exiftool's "-j" option outputs metadata in JSON
    cmd = ["exiftool", "-j", "-u", file_path]
    try:
        # Run exiftool and capture the output
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        # exiftool outputs a JSON array (list of dicts), often with one item
        data = json.loads(result.stdout)
    except subprocess.CalledProcessError as e:
        print(f"Error running exiftool: {e}")
        return
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON from exiftool: {e}")
        print("Raw exiftool output was:")
        print(result.stdout)
        return

    if not data:
        print("No data returned. This could be an empty or non-image file.")
        return

    # exiftool JSON is usually a list with one dict per file, even if you specified only one file
    metadata = data[0]
    for key, value in metadata.items():
        # Some values might be lists, nested dicts, etc. Just stringify them
        # If you want to do more advanced formatting, adjust as needed.
        print(f"{key}: {value}")


def main():
    file_path = r"C:\Photos\unknownFAILSAFE\PXL_20241113_225037037.jpg"
    print(f"Reading metadata with exiftool for: {file_path}")
    print_exif_exiftool(file_path)


if __name__ == "__main__":
    sys.exit(main())
