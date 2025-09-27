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
            return dt_obj.year
    except Exception:
        pass
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
        
        target_dir = os.path.join(base_output_dir, str(dt))

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

def load_ignore_list(ignore_file):
    if not os.path.exists(ignore_file):
        return set()
    with open(ignore_file, "r") as f:
        return set(f.read().splitlines())


def main():
    base_dir = r"D:\sorted"
    root_folder = r"D:\Josie Google"
    ignore_list = r"C:\Coding\ignorelist.txt"
    os.makedirs(base_dir, exist_ok=True)

    ignore_list = load_ignore_list(ignore_list)
    for current_folder, _, files in os.walk(root_folder):
        for entry in files:
            if entry in ignore_list:
                continue
            full_path = os.path.join(current_folder, entry)
            print("Processing", full_path)
            if entry.endswith(".jpg"):
                dt = read_exif_date(full_path)
                if dt:
                    print(f"Found date {dt} for {full_path}")
                    move_file_to_year_folder(full_path, base_dir, dt)
            elif entry.endswith(".mp4"):
                dt = get_mp4_creation_year(full_path)
                if dt:
                    print(f"Found year {dt} for {full_path}")
                    move_file_to_year_folder(full_path, base_dir, dt)

if __name__ == "__main__":
    main()
