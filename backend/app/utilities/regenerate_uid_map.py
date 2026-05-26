import os
import json
from pydicom import dcmread

PERSISTENT_OUTPUT_DIR = "persistent_output"
STUDIES_DIR = os.path.join(PERSISTENT_OUTPUT_DIR, "studies")
UID_MAP_PATH = os.path.join(PERSISTENT_OUTPUT_DIR, "uid_map.json")

def regenerate_uid_map():
    uid_map = {}

    for study_hash in os.listdir(STUDIES_DIR):
        study_path = os.path.join(STUDIES_DIR, study_hash)
        if not os.path.isdir(study_path):
            continue

        for series_hash in os.listdir(study_path):
            series_path = os.path.join(study_path, series_hash)
            if not os.path.isdir(series_path):
                continue

            for file in os.listdir(series_path):
                if file.endswith(".dcm") and not file.endswith("_thumb.jpg"):
                    file_path = os.path.join(series_path, file)
                    try:
                        ds = dcmread(file_path, stop_before_pixels=True)
                        study_uid = ds.StudyInstanceUID
                        series_uid = ds.SeriesInstanceUID
                        sop_uid = ds.SOPInstanceUID

                        # Initialize structure
                        if study_uid not in uid_map:
                            uid_map[study_uid] = {
                                "study_hash": study_hash,
                                "series": {}
                            }
                        if series_uid not in uid_map[study_uid]["series"]:
                            uid_map[study_uid]["series"][series_uid] = {
                                "series_hash": series_hash,
                                "instances": {}
                            }

                        # Map SOPInstanceUID to hashed filename (without extension)
                        sop_hash = file.replace(".dcm", "")
                        uid_map[study_uid]["series"][series_uid]["instances"][sop_uid] = sop_hash

                    except Exception as e:
                        print(f"Error reading {file_path}: {e}")

    with open(UID_MAP_PATH, "w") as f:
        json.dump(uid_map, f, indent=2)
    print(f"✅ UID map regenerated and saved to {UID_MAP_PATH}")

if __name__ == "__main__":
    regenerate_uid_map()
