import os, hashlib, pickle
from pathlib import Path

#try:
  #  import xxhash
 #   has_xxhash = True
#except ImportError:
has_xxhash = False

root_folder = r"D:\Josie Google"
duplicates_folder = r"D:\duplicates"
pickles_dir = r"C:\Coding\hash_pickles"
ignore_list = r"C:\Coding\ignorelist.txt"
completed_folders = r"C:\Coding\completed_folders.txt"
GLOBAL_SIZE_PICKLE = os.path.join(pickles_dir, "global_size_map.pickle")
PARTIAL_THRESHOLD = 50 * 1024 * 1024  # 50MB
PARTIAL_CHUNK_SIZE = 5 * 1024 * 1024    # 5MB
FULL_CHUNK_SIZE = 10 * 1024 * 1024      # 10MB

def load_ignore_list(ignore_file):
    if not os.path.exists(ignore_file):
        return set()
    with open(ignore_file, "r") as f:
        return set(f.read().splitlines())

def compute_full_hash(filepath, chunk_size=FULL_CHUNK_SIZE):
    h = xxhash.xxh64() if has_xxhash else hashlib.md5()
    with open(filepath, "rb") as f:
        while (data := f.read(chunk_size)):
            h.update(data)
    return h.hexdigest()

def compute_partial_hash(filepath, chunk_size=PARTIAL_CHUNK_SIZE):
    h = xxhash.xxh64() if has_xxhash else hashlib.md5()
    filesize = os.path.getsize(filepath)
    with open(filepath, "rb") as f:
        h.update(f.read(chunk_size))
        if filesize > chunk_size:
            f.seek(max(filesize - chunk_size, 0))
            h.update(f.read(chunk_size))
    return h.hexdigest()

def safe_folder_name(folder):
    rel = os.path.relpath(folder, root_folder)
    return "root" if rel == "." else rel.replace(os.sep, "_").replace(":", "")

def get_global_size_map():
    if os.path.exists(GLOBAL_SIZE_PICKLE):
        with open(GLOBAL_SIZE_PICKLE, "rb") as pf:
            return pickle.load(pf)
    
    size_map = {}
    for current_folder, _, files in os.walk(root_folder):
        for entry in files:
            if entry.startswith(".") or ".json" in entry:
                continue
            full_path = os.path.join(current_folder, entry)
            try:
                size = os.path.getsize(full_path)
                size_map[size] = size_map.get(size, 0) + 1
            except Exception as e:
                print(f"Error getting size for {full_path}: {e}")
    with open(GLOBAL_SIZE_PICKLE, "wb") as pf:
        pickle.dump(size_map, pf)
    return size_map

def process_folder(folder, pickle_dir, size_map):
    safe_name = safe_folder_name(folder)
    if safe_name in open(completed_folders).read():
        print(f"Folder '{folder}' already processed; skipping.")
        return
    pickle_file = os.path.join(pickle_dir, f"{safe_name}.pickle")
    if os.path.exists(pickle_file):
        with open(pickle_file, "rb") as pf:
            folder_data = pickle.load(pf)
    else:
        folder_data = {'full': {}, 'partial': {}}
    processed_files = set()
    for cat in folder_data.values():
        for paths in cat.values():
            processed_files.update(paths)
    print(f"Starting folder '{folder}'.")
    new_count = 0
    files_list = os.listdir(folder)
    ignore_files = load_ignore_list(ignore_list)
    for idx, entry in enumerate(files_list, 1):
        if entry in ignore_files:
            continue 
        full_path = os.path.join(folder, entry)
        if not (os.path.isfile(full_path) and not entry.startswith(".") and ".json" not in entry):
            continue
        print("Processing file", idx, "of", len(files_list), ":", full_path)
        if full_path in processed_files:
            continue
        try:
            size = os.path.getsize(full_path)
        except Exception as e:

            print(f"Error getting size for {full_path}: {e}")
            continue
        if size_map.get(size, 0) < 2:
            continue
        if size < PARTIAL_THRESHOLD:
           # try:
           #     filehash = compute_full_hash(full_path)
           # except Exception as e:
           #     with open(ignore_list, "a") as f:
           #         f.write(safe_name + "\n")
           #         print(f"Error computing full hash for {full_path}")
           #         continue
                
            filehash = compute_full_hash(full_path)
            if filehash:
                folder_data['full'].setdefault(filehash, []).append(full_path)
        else:
            p_hash = compute_partial_hash(full_path)
            if p_hash:
                key = (size, p_hash)
                folder_data['partial'].setdefault(key, []).append(full_path)
        processed_files.add(full_path)
        new_count += 1
        if new_count % 10 == 0:
            print(f"Processed {new_count} new files in folder '{folder}'.")
        if new_count % 100 == 0:
            with open(pickle_file, "wb") as pf:
                pickle.dump(folder_data, pf)
    with open(pickle_file, "wb") as pf:
        pickle.dump(folder_data, pf)
    print(f"Completed folder '{folder}'; pickle saved to '{pickle_file}'.")
    with open(completed_folders, "a") as f:
        f.write(safe_name + "\n")

def combine_pickles(pickle_dir):
    combined_full = {}
    partial_candidates = {}
    for fname in os.listdir(pickle_dir):
        if fname.endswith(".pickle"):
            full_path = os.path.join(pickle_dir, fname)
            try:
                with open(full_path, "rb") as pf:
                    data = pickle.load(pf)
                for fh, paths in data.get('full', {}).items():
                    combined_full.setdefault(fh, []).extend(paths)
                for key, paths in data.get('partial', {}).items():
                    partial_candidates.setdefault(key, []).extend(paths)
            except Exception as e:
                print(f"Error loading pickle file {full_path}: {e}")
    with open(os.path.join(duplicates_folder, "partial_candidates.pickle"), "wb") as f:
        pickle.dump(partial_candidates,f)
    with open(os.path.join(duplicates_folder, "combined_full.pickle"), "wb") as f:
        pickle.dump(combined_full,f)
    return partial_candidates, combined_full

def complete_partial_hashes(partial_candidates, combined_full):
    for key, paths in partial_candidates.items():
        path_text = Path(paths)
        if path_text.name in ignore_list:
            print(f"Skipping partial hash for {path}")
            continue
        if len(paths) > 1:
            for path in paths:
                print(f"Processing partial hash for {path}")
                full_hash = compute_full_hash(path)
                if full_hash:
                    combined_full.setdefault(full_hash, []).append(path)
    return combined_full


def main():
    if not os.path.exists(pickles_dir):
        os.makedirs(pickles_dir)
    if not os.path.exists(duplicates_folder):
        os.makedirs(duplicates_folder)
    print("Building global file size map...")
    global_size_map = get_global_size_map()
    print("Global file size map built.")

    #use this loop for initial hash creation
    #for current_folder, _, _ in os.walk(root_folder):
    #   process_folder(current_folder, pickles_dir, global_size_map)
    
    #create a single pickled for full hashes and partial hashes
    partial, full = combine_pickles(pickles_dir)

    final_hash_map = complete_partial_hashes(partial, full)
    print(f"\nCombined hash map contains {len(final_hash_map)} unique full hashes.")
    final_output = os.path.join(duplicates_folder, "final_hash_map.pickle")
    try:
        with open(final_output, "wb") as f:
            pickle.dump(final_hash_map, f)
        print(f"Final combined hash map saved to '{final_output}'.")
    except Exception as e:
        print(f"Error saving final combined hash map: {e}")
    print("\nAll done!") 

if __name__ == "__main__":
    main()
