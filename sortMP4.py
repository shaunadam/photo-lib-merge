import os
import shutil
from pymediainfo import MediaInfo
from datetime import datetime


def get_mp4_creation_year(filepath):
    """
    Attempts to read the 'creation' or 'recorded' date from an MP4 file’s metadata.
    Returns an integer year (e.g., 2024) if successful, otherwise None.
    """
    media_info = MediaInfo.parse(filepath)
    for track in media_info.tracks:
        if track.track_type == "General":
            # Some MP4s store creation date in 'recorded_date', 'tagged_date',
            # 'encoded_date', or 'creation_date'.
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
                    # Now the string looks like '2016-06-16 14:55:09 +0000'

                # Try various parse patterns:
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


def move_unknown_mp4s_by_metadata(
    unknown_folder=r"C:/Photos/unknown",
    josie_folder=r"C:/Photos",
):
    """
    Checks each MP4 in `unknown_folder`, attempts to get its creation year via metadata,
    and moves it to `C:/Photos/Josie/YYYY` or `C:/Photos/Josie/unknown`.
    """
    if not os.path.exists(unknown_folder):
        print(f"Unknown folder not found: {unknown_folder}")
        return

    if not os.path.exists(josie_folder):
        os.makedirs(josie_folder)
    OG = len(os.listdir(unknown_folder))
    for filename in os.listdir(unknown_folder):
        if not filename.lower().endswith(".mp4"):
            continue  # skip non-MP4 files

        file_path = os.path.join(unknown_folder, filename)
        if not os.path.isfile(file_path):
            continue

        # Try to parse the creation year from metadata
        year = get_mp4_creation_year(file_path)

        if year is not None:
            # e.g. 2024 => "2024"
            target_subfolder = str(year)
        else:
            # If we can’t determine the year, put in "unknown"
            target_subfolder = "unknown"

        # Construct final destination folder: e.g. C:/Photos/Josie/2024
        dest_folder = os.path.join(josie_folder, target_subfolder)
        if not os.path.exists(dest_folder):
            os.makedirs(dest_folder)

        dest_path = os.path.join(dest_folder, filename)

        # Move the file
        try:
            shutil.move(file_path, dest_path)
            print(f"Moved {file_path} -> {dest_path}")
        except Exception as e:
            print(f"Error moving file {file_path}: {e}")
    print(f"Moved {OG-len(os.listdir(unknown_folder))} files")


if __name__ == "__main__":
    move_unknown_mp4s_by_metadata()
