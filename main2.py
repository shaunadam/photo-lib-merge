import os
import hashlib
import json
import shutil
import zipfile
from datetime import datetime
from zoneinfo import ZoneInfo
import piexif
from piexif._exceptions import InvalidImageDataError
import pickle
from pymediainfo import MediaInfo

# ---------------------------------------------------------------------
# Adjust these paths/configuration as needed
# ---------------------------------------------------------------------

ZIP_FOLDER = r"C:\Users\shaun\Downloads\Takeout"
UNZIPPED_TAKEOUT_DIR = r"C:\Users\shaun\Downloads\Takeout\Unzipped"
ORGANIZED_PHOTOS_DIR = r"C:\Photos"
JSON_BACKUPS_DIR = r"C:\JSON_Backups"
MST_TZ = ZoneInfo("America/Edmonton")


# ---------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------
def unzip_one_takeout_zip(zip_path, extract_target):
    """
    Unzip a single Takeout zip into extract_target.
    """
    os.makedirs(extract_target, exist_ok=True)
    print(f"Unzipping {zip_path} ...")
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(extract_target)


def find_files_recursive(base_dir):
    """
    Recursively yield full file paths under base_dir.
    """
    for root, dirs, files in os.walk(base_dir):
        for fname in files:
            if fname.startswith("."):
                continue
            yield os.path.join(root, fname)


def get_json_date(json_path):
    """
    Parse a Google Photos JSON file to retrieve a date.
    Return a Python datetime in UTC (still naive, or aware with UTC).
    Priority: photoTakenTime -> creationTime.
    If neither is available, return None.
    """
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if "photoTakenTime" in data and "timestamp" in data["photoTakenTime"]:
        ts_str = data["photoTakenTime"]["timestamp"]
    elif "creationTime" in data and "timestamp" in data["creationTime"]:
        ts_str = data["creationTime"]["timestamp"]
    else:
        return None

    ts = int(ts_str)
    dt_utc = datetime.fromtimestamp(ts, ZoneInfo("UTC"))
    return dt_utc


def read_exif_date(image_path):
    """
    Read EXIF 'DateTimeOriginal' from the file. Return a datetime (UTC-naive),
    or None if not found or if file has no EXIF.
    """
    try:
        exif_dict = piexif.load(image_path)
        datetime_str = exif_dict["Exif"].get(piexif.ExifIFD.DateTimeOriginal, None)
        if datetime_str:
            # Typically in format "YYYY:MM:DD HH:MM:SS"
            dt_obj = datetime.strptime(
                datetime_str.decode("utf-8"), "%Y:%m:%d %H:%M:%S"
            )
            return dt_obj
    except Exception:
        pass
    return None


def get_mp4_creation_year(filepath):
    """
    Attempts to read the 'creation' or 'recorded' date from an MP4 file’s metadata.
    Returns an integer year (e.g., 2024) if successful, otherwise None.
    """
    try:
        media_info = MediaInfo.parse(filepath)
        for track in media_info.tracks:
            if track.track_type == "General":
                possible_fields = [
                    track.recorded_date,
                    track.tagged_date,
                    track.encoded_date,
                    track.creation_date,
                ]
                for field_value in possible_fields:
                    if not field_value:
                        continue

                    # If the string ends with ' UTC', replace it with ' +0000'
                    # so that Python can parse it with %z.
                    if field_value.endswith(" UTC"):
                        field_value = field_value.replace(" UTC", " +0000")

                    for fmt in (
                        "%Y-%m-%d %H:%M:%S %z",
                        "%Y-%m-%d %H:%M:%S.%f %z",
                        "%Y-%m-%d %H:%M:%S",
                        "%Y-%m-%dT%H:%M:%S",
                        "%Y-%m-%dT%H:%M:%S%z",
                        "%Y-%m-%d %H:%M:%S%z",
                    ):
                        try:
                            dt = datetime.strptime(field_value, fmt)
                            return dt.year
                        except ValueError:
                            pass
        return None
    except Exception as e:
        print(f"Error reading MP4 metadata for {filepath}: {e}")
        return None


def get_final_date_for_file(file_path, json_date_utc):
    """
    Decide which date to use:
      1. If EXIF date is present, return that (do NOT overwrite).
      2. If no EXIF date, use the JSON date (converted from UTC -> MST).
      3. If neither is available, return None.
    """
    # Special handling for MP4
    if file_path.lower().endswith(".mp4"):
        dt = get_mp4_creation_year(file_path)
        if dt is not None:
            return datetime(dt, 1, 1)
        elif json_date_utc is not None:
            dt_mst = json_date_utc.replace(tzinfo=ZoneInfo("UTC")).astimezone(MST_TZ)
            return dt_mst.replace(tzinfo=None)
    else:
        dt = read_exif_date(file_path)
        if dt is not None:
            return dt
        if json_date_utc is not None:
            dt_mst = json_date_utc.replace(tzinfo=ZoneInfo("UTC")).astimezone(MST_TZ)
            return dt_mst.replace(tzinfo=None)
    return None


def get_unique_path(path):
    """
    If 'path' already exists on disk, append ' (1)', ' (2)', etc. until it's unique.
    """
    if not os.path.exists(path):
        return path

    base, ext = os.path.splitext(path)
    count = 1
    while True:
        candidate = f"{base} ({count}){ext}"
        if not os.path.exists(candidate):
            return candidate
        count += 1


def move_file_to_year_folder(file_path, base_output_dir, dt):
    """
    Move file to a year-based folder in base_output_dir.
    If dt is None, move to 'unknown' folder.
    If the filename already exists, rename to avoid overwrite.
    """
    if dt is None:
        target_dir = os.path.join(base_output_dir, "unknown")
    else:
        year_str = str(dt.year)
        target_dir = os.path.join(base_output_dir, year_str)

    os.makedirs(target_dir, exist_ok=True)

    filename = os.path.basename(file_path)
    final_path = os.path.join(target_dir, filename)

    # Ensure uniqueness
    final_path = get_unique_path(final_path)

    try:
        shutil.move(file_path, final_path)
    except Exception as e:
        print(f"Error moving file {file_path} to {final_path}: {e}")
    return final_path


def process_google_photos_and_dedupe(unzipped_dir):
    """
    Process JSON + associated media.
    If the JSON indicates family sharing, skip. Otherwise:
      - Determine date from JSON or EXIF
      - Move the file to year folder
      - Delete the JSON
    """
    print(
        f"Scanning unzipped Google Photos directory for JSON files in: {unzipped_dir}"
    )
    for fpath in find_files_recursive(unzipped_dir):
        if fpath.lower().endswith(".json"):
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)

            google_origin = data.get("googlePhotosOrigin", {})
            if "fromPartnerSharing" not in google_origin:
                base_file = fpath[:-5]  # remove ".json"
                json_date_utc = get_json_date(fpath)
                print(f"Moving file for {os.path.basename(base_file)}...")

                move_file_to_year_folder(base_file, ORGANIZED_PHOTOS_DIR, json_date_utc)

            # Regardless of family sharing or not,
            # we can delete JSON after checking it or keep it if you prefer
            try:
                os.remove(fpath)
            except OSError as e:
                print(f"Error deleting JSON file {fpath}: {e}")


def main():
    # Get a list of all zip files in ZIP_FOLDER
    zip_files = [
        f
        for f in os.listdir(ZIP_FOLDER)
        if f.lower().endswith(".zip") and f.startswith("takeout-")
    ]

    for fname in zip_files:
        zip_path = os.path.join(ZIP_FOLDER, fname)
        # 1) Create a temporary extraction folder for this one zip
        temp_unzip_dir = os.path.join(ZIP_FOLDER, "UnzippedTemp")

        # Make sure it's empty or doesn’t exist
        if os.path.exists(temp_unzip_dir):
            shutil.rmtree(temp_unzip_dir)
        os.makedirs(temp_unzip_dir, exist_ok=True)

        # 2) Unzip the current file
        unzip_one_takeout_zip(zip_path, temp_unzip_dir)

        # 3) Process the unzipped contents
        print(f"Processing unzipped contents from {zip_path} ...")
        process_google_photos_and_dedupe(temp_unzip_dir)

        # -- FAILSAFE: Move leftover non-JSON files into 'unknown' folder (with rename if needed) --
        # -- FAILSAFE: Move leftover non-JSON files into unknown-type folders with rename if needed --
        for leftover_file in find_files_recursive(temp_unzip_dir):
            if not leftover_file.lower().endswith(".json"):
                # 1) Check if there's a matching .json file by appending ".json"
                potential_json = leftover_file + ".json"
                if os.path.exists(potential_json):
                    # 2) Read the JSON and check for fromPartnerSharing
                    with open(potential_json, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    google_origin = data.get("googlePhotosOrigin", {})

                    # If fromPartnerSharing is present => unknownPARTNER
                    if "fromPartnerSharing" in google_origin:
                        dir_to_use = "unknownPARTNER"
                    else:
                        # JSON was found, but not partner sharing => unknown
                        dir_to_use = "unknown"
                else:
                    # 3) No JSON found => unknownFAILSAFE
                    dir_to_use = "unknownFAILSAFE"

                # Create the appropriate directory
                final_dir = os.path.join(ORGANIZED_PHOTOS_DIR, dir_to_use)
                os.makedirs(final_dir, exist_ok=True)

                # Build a unique path (in case a file of the same name already exists)
                leftover_filename = os.path.basename(leftover_file)
                final_path = os.path.join(final_dir, leftover_filename)
                final_path = get_unique_path(final_path)

                # Move leftover file
                try:
                    shutil.move(leftover_file, final_path)
                except Exception as e:
                    print(
                        f"Error moving leftover file {leftover_file} to {final_path}: {e}"
                    )

        # 4) Delete the temp folder
        shutil.rmtree(temp_unzip_dir, ignore_errors=True)

        # (Optional) If you no longer need the original zip, delete it:
        os.remove(zip_path)

    print("\nAll done!")


if __name__ == "__main__":
    main()
