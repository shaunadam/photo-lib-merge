import piexif
import sys


def print_exif(file_path):
    # Load the EXIF data into a dictionary
    exif_dict = piexif.load(file_path)

    for ifd_name in exif_dict:
        # If the IFD data is None, skip it
        if exif_dict[ifd_name] is None:
            print(f"=== IFD: {ifd_name} is empty (None) ===")
            continue

        print(f"=== IFD: {ifd_name} ===")

        for tag_id, value in exif_dict[ifd_name].items():
            tag_name = (
                piexif.TAGS[ifd_name]
                .get(tag_id, {})
                .get("name", f"UnknownTag_{tag_id}")
            )

            if isinstance(value, bytes):
                try:
                    value = value.decode("utf-8", errors="replace")
                except Exception:
                    pass  # just leave it as bytes if decoding fails

            print(f"  {tag_id} - {tag_name}: {value}")


def main():
    file_path = r"C:\Photos\unknownFAILSAFE\PXL_20241113_225037037.jpg"
    print_exif(file_path)


if __name__ == "__main__":
    sys.exit(main())
