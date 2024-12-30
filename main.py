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

# ---------------------------------------------------------------------
# Adjust these paths/configuration as needed
# ---------------------------------------------------------------------

# 1. Folder containing the 53 zip files:
#    takeout-20241228T214429Z-001.zip up to -053.zip
ZIP_FOLDER = r"C:\Users\shaun\Downloads\Takeout"

# 2. Where to extract the contents of the zip files
UNZIPPED_TAKEOUT_DIR = r"C:\Users\shaun\Downloads\Takeout\Unzipped"

# 3. The base output directory for organized Google Photos
#    (where we place yearly or unknown folders)
ORGANIZED_PHOTOS_DIR = r"C:\Photos"

# 4. Your OneDrive root folder
ONEDRIVE_DIR = r"C:\Users\shaun\OneDrive"

# 5. Single duplicates folder (where suspected duplicates from OneDrive will be moved)
ONEDRIVE_DUPLICATES_DIR = r"C:\Users\shaun\OneDrive\duplicates"

# 6. The timezone you want to convert from UTC to MST
MST_TZ = ZoneInfo("America/Edmonton")

# ---------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------


def unzip_takeout_zips(zip_folder, extract_target):
    """
    Unzip all files matching 'takeout-*.zip' from zip_folder into extract_target.
    """
    os.makedirs(extract_target, exist_ok=True)
    for fname in os.listdir(zip_folder):
        if fname.lower().endswith(".zip") and fname.startswith("takeout-"):
            zip_path = os.path.join(zip_folder, fname)
            print(f"Unzipping {zip_path} ...")
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(extract_target)
    print("All Takeout .zip files have been extracted.")


def compute_file_hash(filepath, chunk_size=65536):
    """
    Compute an MD5 hash of a file’s contents.
    """
    md5 = hashlib.md5()
    with open(filepath, "rb") as f:
        while True:
            data = f.read(chunk_size)
            if not data:
                break
            md5.update(data)
    return md5.hexdigest()


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
    # try:
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    # e.g.,
    # {
    #   "creationTime": {"timestamp": "1636834808"},
    #   "photoTakenTime": {"timestamp": "1528900621"},
    #   ...
    # }
    if "photoTakenTime" in data and "timestamp" in data["photoTakenTime"]:
        ts_str = data["photoTakenTime"]["timestamp"]
    elif "creationTime" in data and "timestamp" in data["creationTime"]:
        ts_str = data["creationTime"]["timestamp"]
    else:
        return None

    # Convert string timestamp to int, then to a UTC datetime
    ts = int(ts_str)
    dt_utc = datetime.fromtimestamp(ts, ZoneInfo("UTC"))
    return dt_utc


# except Exception as e:
#   print(f"Error parsing JSON {json_path}: {e}")
#  return None


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


def write_exif_date(image_path, dt):
    """
    Supplement the existing EXIF data with a 'DateTimeOriginal' (and 'DateTimeDigitized')
    only if it's missing or invalid. We don't overwrite any existing valid date.

    :param image_path: Full path to the image.
    :param dt: A Python datetime object (assumed local time) to write if missing.
    """
    try:
        exif_dict = piexif.load(image_path)
    except Exception:
        # If the image has no EXIF segment, create a minimal structure
        exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}

    # Format the datetime as EXIF expects: "YYYY:MM:DD HH:MM:SS"
    dt_str = dt.strftime("%Y:%m:%d %H:%M:%S").encode("utf-8")

    # Check if DateTimeOriginal is missing or set to a 'zero' placeholder
    existing_dtorig = exif_dict["Exif"].get(piexif.ExifIFD.DateTimeOriginal, b"")
    if not existing_dtorig or existing_dtorig == b"0000:00:00 00:00:00":
        exif_dict["Exif"][piexif.ExifIFD.DateTimeOriginal] = dt_str

    # Check if DateTimeDigitized is missing or set to a 'zero' placeholder
    existing_dtdig = exif_dict["Exif"].get(piexif.ExifIFD.DateTimeDigitized, b"")
    if not existing_dtdig or existing_dtdig == b"0000:00:00 00:00:00":
        exif_dict["Exif"][piexif.ExifIFD.DateTimeDigitized] = dt_str

    # Optionally, also supplement the "0th" DateTime if you want it consistent.
    # Many apps interpret this as the file's main timestamp. If you want to leave it alone,
    # feel free to comment out. Otherwise:
    existing_dt0th = exif_dict["0th"].get(piexif.ImageIFD.DateTime, b"")
    if not existing_dt0th or existing_dt0th == b"0000:00:00 00:00:00":
        exif_dict["0th"][piexif.ImageIFD.DateTime] = dt_str

    # Save updated EXIF
    exif_bytes = piexif.dump(exif_dict)
    try:
        piexif.insert(exif_bytes, image_path)
    except InvalidImageDataError:
        print(f"Skipping file with invalid data: {image_path}")


def get_final_date_for_file(file_path, json_date_utc):
    """
    Decide which date to use:
      1. If EXIF date is present, return that (do NOT overwrite).
      2. If no EXIF date, use the JSON date (converted from UTC -> MST).
      3. If neither is available, return None.
    """
    exif_dt = read_exif_date(file_path)
    if exif_dt is not None:
        # If EXIF date is found, just return that.
        return exif_dt
    else:
        # If no EXIF, but we have JSON date, convert it to MST
        if json_date_utc is not None:
            # Convert from naive UTC to MST
            dt_mst = json_date_utc.replace(tzinfo=ZoneInfo("UTC")).astimezone(MST_TZ)
            # Convert back to naive local time (if you want the EXIF to just hold local time)
            dt_naive = dt_mst.replace(tzinfo=None)
            # Write EXIF date
            write_exif_date(file_path, dt_naive)
            return dt_naive
        else:
            return None


def move_file_to_year_folder(file_path, base_output_dir, dt):
    """
    Move file to a year-based folder in base_output_dir.
    If dt is None, move to 'unknown' folder.
    """
    if dt is None:
        target_dir = os.path.join(base_output_dir, "unknown")
    else:
        year_str = str(dt.year)
        target_dir = os.path.join(base_output_dir, year_str)

    os.makedirs(target_dir, exist_ok=True)

    filename = os.path.basename(file_path)
    new_path = os.path.join(target_dir, filename)

    # Move (not copy) so we don't leave duplicates behind
    shutil.move(file_path, new_path)
    return new_path


def build_onedrive_hashmap(onedrive_dir):
    """
    Recursively hash files in OneDrive, building a dict: { filehash: [list_of_paths] }.
    Skip the duplicates folder itself to avoid re-checking moved files.
    """
    onedrive_map = {}
    for fpath in find_files_recursive(onedrive_dir):
        # Skip the duplicates folder
        if ONEDRIVE_DUPLICATES_DIR in fpath:
            continue
        if any((r"OneDrive\Photos" in fpath, r"OneDrive\Pictures" in fpath)):
            filehash = compute_file_hash(fpath)
            if filehash not in onedrive_map:
                onedrive_map[filehash] = []
            onedrive_map[filehash].append(fpath)
            print(f"Created hash for {fpath}")
    return onedrive_map


def process_google_photos_and_dedupe():
    """
    1) Recursively find files in the unzipped Google Photos folder (UNZIPPED_TAKEOUT_DIR).
    2) Pair each file with its JSON if present.
    3) Read or write EXIF date as needed.
    4) Move the file into a year-based folder under ORGANIZED_PHOTOS_DIR.
    5) Check for duplicates in OneDrive; move the OneDrive file(s) to duplicates if a match.
    """
    if os.path.getsize("OD.hash") > 0:
        f = open("OD.hash", "rb")
        onedrive_map = pickle.load(f)
        f.close()
    else:
        print("Building OneDrive file hash map...")
        onedrive_map = build_onedrive_hashmap(ONEDRIVE_DIR)
        f = open("OD.hash", "wb")
        pickle.dump(onedrive_map, f)
        f.close()
        print(f"OneDrive map complete. Found {len(onedrive_map)} unique hashes.\n")

    # Step A: Gather JSON metadata in a dictionary
    json_dates = {}
    if os.path.getsize("dates.dict") > 0:
        f = open("dates.dict", "rb")
        json_dates = pickle.load(f)
        f.close()
    else:
        print("Scanning unzipped Google Photos directory for JSON files...")
        for fpath in find_files_recursive(UNZIPPED_TAKEOUT_DIR):
            if fpath.lower().endswith(".json"):
                # Potentially a Google Photos metadata file
                base_file = fpath[:-5]  # remove ".json" to get the corresponding file
                json_date_utc = get_json_date(fpath)
                if json_date_utc is not None:
                    json_dates[base_file] = json_date_utc
                    print(base_file)

        f = open("dates.dict", "wb")
        pickle.dump(json_dates, f)
        f.close()

    # Step B: For each actual file (non-JSON)
    print("Processing unzipped Google Photos files (non-JSON) and organizing...")
    for fpath in find_files_recursive(UNZIPPED_TAKEOUT_DIR):
        if fpath.lower().endswith(".json"):
            continue  # skip .json files themselves
        if fpath.lower().endswith(".jpg"):
            # 1. Determine JSON-based date if available
            json_date_utc = json_dates.get(fpath)

            # 2. Read EXIF if present, else write from JSON
            final_dt = get_final_date_for_file(fpath, json_date_utc)
        print(f'Moving {fpath.split('\\')[-1]}')
        # 3. Move file to year-based folder
        new_path = move_file_to_year_folder(fpath, ORGANIZED_PHOTOS_DIR, final_dt)

        # 4. Check duplicates in OneDrive
        new_file_hash = compute_file_hash(new_path)
        if new_file_hash in onedrive_map:
            # For each OneDrive file that shares this hash, move it to the duplicates folder
            for dup_path in onedrive_map[new_file_hash]:
                rel_name = os.path.basename(dup_path)
                duplicates_target = os.path.join(ONEDRIVE_DUPLICATES_DIR, rel_name)
                os.makedirs(ONEDRIVE_DUPLICATES_DIR, exist_ok=True)
                print(f"Moving OneDrive duplicate to {duplicates_target}")
                shutil.move(dup_path, duplicates_target)

            # Remove that hash from the map to avoid re-checking
            del onedrive_map[new_file_hash]


def main():
    """
    Main entry point.
    1) Unzip all Takeout zips from ZIP_FOLDER to UNZIPPED_TAKEOUT_DIR
    2) Process the unzipped Google Photos
    3) Deduplicate with OneDrive
    """
    # 1) Unzip all the takeout-*.zip files
    print(f"Unzipping all zips from {ZIP_FOLDER} to {UNZIPPED_TAKEOUT_DIR}...")
    unzip_takeout_zips(ZIP_FOLDER, UNZIPPED_TAKEOUT_DIR)

    # 2) Make sure the duplicates folder exists
    os.makedirs(ONEDRIVE_DUPLICATES_DIR, exist_ok=True)

    # 3) Process Google Photos and remove duplicates in OneDrive
    print("Starting Google Photos processing and OneDrive deduplication...")
    process_google_photos_and_dedupe()
    print("\nAll done!")


if __name__ == "__main__":
    main()
