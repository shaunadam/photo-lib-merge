import os
import pickle

f = open("D:\duplicates\combined_full.pickle", "rb")
hash_map = pickle.load(f)
f.close()

duplicates = {}
print(f"Original hash map is of length {len(hash_map)}")
for hash, paths in hash_map.items():
    if len(paths) > 1:
        duplicates[hash] = paths
print(f"Found {len(duplicates)} duplicates")


def customsort(x):

    # Prefer shorter filenames
    filename_length = len(os.path.basename(x))
    filepath_length = len(x)

    return (filepath_length,filename_length)


for key, value in duplicates.items():
    if len(value) > 1:
        value.sort(key=lambda x: customsort(x))
        print(f"sorted paths:{value}")
        for i in value[1:]:
            print(f"delete: {i}")
            try:
                os.remove(i)
            except Exception as e:
                pass
