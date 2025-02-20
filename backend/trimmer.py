from fitparse import FitFile
import pandas as pd
import xml.etree.ElementTree as ET
import os

UPLOAD_FOLDER = "uploads"

def load_fit(file_path):
    fitFile = FitFile(file_path)
    records = []

    for record in fitFile.get_messages("record"):
        record_data = record.get_values()
        records.append({
            "timestamp": record_data.get("timestamp"),
            "distance": record_data.get("distance"),
            "heart_rate": record_data.get("heart_rate"),
        })
    
    return pd.DataFrame(records)

def detect_stop(df):
    df = df.dropna(subset=["distance"])
    df = df.copy()
    df["distance_diff"] = df["distance"].diff()

    for index, row in df.iterrows():
        if row["distance_diff"] == 0:
            return row["timestamp"]
    
    return df["timestamp"].max()

def trim(df, end_timestamp):
    return df[df["timestamp"] < end_timestamp]

def convert_to_tcx(df, output_file):
    tcx = ET.Element("TrainingCenterDatabase", {
        "xmlns": "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"
    })
    
    activities = ET.SubElement(tcx, "Activities")
    activity = ET.SubElement(activities, "Activity", Sport="Running")

    start_time = df["timestamp"].iloc[0].isoformat() + "Z"
    ET.SubElement(activity, "Id").text = start_time

    lap = ET.SubElement(activity, "Lap", StartTime=start_time)
    ET.SubElement(lap, "TotalTimeSeconds").text = str((df["timestamp"].max() - df["timestamp"].min()).total_seconds())
    ET.SubElement(lap, "DistanceMeters").text = str(df["distance"].max())

    track = ET.SubElement(lap, "Track")

    for _, row in df.iterrows():
        trackpoint = ET.SubElement(track, "Trackpoint")
        ET.SubElement(trackpoint, "Time").text = row["timestamp"].isoformat() + "Z"

        if not pd.isna(row["distance"]):
            ET.SubElement(trackpoint, "DistanceMeters").text = str(row["distance"])

        if not pd.isna(row["heart_rate"]):
            heart_rate_element = ET.SubElement(trackpoint, "HeartRateBpm")
            ET.SubElement(heart_rate_element, "Value").text = str(int(row["heart_rate"]))

    tree = ET.ElementTree(tcx)
    tree.write(output_file, encoding="utf-8", xml_declaration=True)

    return output_file

def process_file(file_path):
    df = load_fit(file_path)
    end_timestamp = detect_stop(df)
    trimmed_df = trim(df, end_timestamp)

    trimmed_tcx = os.path.join(UPLOAD_FOLDER, "trimmed_" + os.path.basename(file_path).replace(".fit", ".tcx"))
    convert_to_tcx(trimmed_df, trimmed_tcx)

    return trimmed_tcx
