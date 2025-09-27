import os


root_folder = r"D:\Josie Google"
for current_folder, _, files in os.walk(root_folder):
        for entry in files:
            if entry.endswith(".json"):
                full_path = os.path.join(current_folder, entry)
                try:
                    #print(f"delete: {full_path}")
                    os.remove(full_path)
                except Exception as e:
                     pass