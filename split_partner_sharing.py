import os
import json
import shutil
import re


def move_partner_sharing_photos(
    json_folder=r"C:/JSON_Backups",
    photos_folder=r"C:/Photos",
    josie_folder=r"C:/Photos/Josie",
):
    """
    Moves media files associated with JSON files containing 'fromPartnerSharing'
    to a matching subfolder under 'C:/Photos/Josie/'.
    """

    # Regex to strip trailing "(n)" at the end of a filename (before any extension).
    # e.g. "photo1.jpeg(1)" -> "photo1.jpeg"
    parenthetical_pattern = re.compile(r"\(\d+\)$")

    # 1. Ensure the "Josie" folder exists
    if not os.path.exists(josie_folder):
        os.makedirs(josie_folder)

    # 2. List all subfolders in photos_folder (these should be the years and "unknown")
    #    We'll exclude the Josie folder to avoid scanning it for matching media.
    subfolders = [
        f
        for f in os.listdir(photos_folder)
        if os.path.isdir(os.path.join(photos_folder, f)) and f.lower() != "josie"
    ]

    # 3. Go through each JSON file in the json_folder
    for json_filename in os.listdir(json_folder):
        if not json_filename.lower().endswith(".json"):
            continue  # Skip non-JSON files

        json_path = os.path.join(json_folder, json_filename)
        try:
            # 4. Parse the JSON
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"Skipping {json_filename}: Error reading JSON ({e})")
            continue

        # 5. Check if 'fromPartnerSharing' is present in the JSON
        google_origin = data.get("googlePhotosOrigin", {})
        if "fromPartnerSharing" not in google_origin:
            # Not from partner sharing, skip
            continue

        # 6. Derive media filename from the JSON filename
        #    e.g. "photo1.jpeg(1).json" -> "photo1.jpeg(1)"
        base_media_name = json_filename.rsplit(".json", 1)[0]

        # 6.1 Also try to strip off trailing parenthetical (e.g. "(1)")
        #     so if the JSON file is "photo1.jpeg(1).json", we also try "photo1.jpeg"
        stripped_name = parenthetical_pattern.sub("", base_media_name)

        # We'll try both the original name and the stripped one:
        possible_names = [base_media_name]
        if stripped_name != base_media_name:
            possible_names.append(stripped_name)

        # 7. Look for the media file in the known subfolders (YYYY or unknown)
        media_found = False
        for subfolder in subfolders:
            subfolder_path = os.path.join(photos_folder, subfolder)

            for candidate_name in possible_names:
                candidate_path = os.path.join(subfolder_path, candidate_name)
                if os.path.exists(candidate_path):
                    # We found the matching media file
                    media_found = True

                    # Construct the Josie subfolder path that mirrors the original subfolder name
                    josie_subfolder_path = os.path.join(josie_folder, subfolder)
                    if not os.path.exists(josie_subfolder_path):
                        os.makedirs(josie_subfolder_path)

                    # Build the new path in the Josie subfolder
                    new_media_path = os.path.join(josie_subfolder_path, candidate_name)

                    # 8. Move the file
                    try:
                        shutil.move(candidate_path, new_media_path)
                        print(f"Moved: {candidate_path} -> {new_media_path}")
                    except Exception as e:
                        print(f"Error moving {candidate_path} -> {new_media_path}: {e}")

                    # Once moved, stop checking this JSON file
                    break

            if media_found:
                break

        if not media_found:
            # If there's no matching media file, we do nothing
            print(f"No matching media file found for {json_filename}")


if __name__ == "__main__":
    move_partner_sharing_photos()
