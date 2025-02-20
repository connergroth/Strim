from fitparse import FitFile
import pandas as pd
import xml.etree.ElementTree as ET

file = "Night_Run.fit"

def load_fit(file):
    fitFile = FitFile(file)
    records = []

    for record in fitFile.get_messages("record"):
        record_data = record.get_values()
        records.append({
            "timestamp":  record_data.get("timestamp"),
            "distance": record_data.get("distance"),
            "heart_rate": record_data.get("heart_rate"),
        })
    
    return pd.DataFrame(records)

def detect_stop(df):
    df = df.dropna(subset=["distance"])  # Remove NaN distance values
    df = df.copy()  # Create a safe copy of df
    df["distance_diff"] = df["distance"].diff()

    for index, row in df.iterrows():
        if row["distance_diff"] == 0:
            endTimestamp = row["timestamp"]
            print(f"Stopped at {endTimestamp}")
            break

    if endTimestamp is None:
        print("Warning: No stop detected!")
        return df["timestamp"].max() # Default to last timestamp 

    return endTimestamp

def trim(endTimeStamp, df):
    df_trimmed = df[df["timestamp"] < endTimeStamp]

    return df_trimmed


def convert_to_tcx(df, output_file="trimmed_run.tcx"):
    # Create XML structure
    tcx = ET.Element("TrainingCenterDatabase", {
        "xmlns": "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"
    })
    
    activities = ET.SubElement(tcx, "Activities")
    activity = ET.SubElement(activities, "Activity", Sport="Running")

    # Use the first timestamp as the activity start time
    start_time = df["timestamp"].iloc[0].isoformat() + "Z"
    ET.SubElement(activity, "Id").text = start_time

    lap = ET.SubElement(activity, "Lap", StartTime=start_time)
    ET.SubElement(lap, "TotalTimeSeconds").text = str((df["timestamp"].max() - df["timestamp"].min()).total_seconds())
    ET.SubElement(lap, "DistanceMeters").text = str(df["distance"].max())
    
    track = ET.SubElement(lap, "Track")

    # Loop through the DataFrame and create trackpoints
    for _, row in df.iterrows():
        trackpoint = ET.SubElement(track, "Trackpoint")

        # Format timestamp correctly
        ET.SubElement(trackpoint, "Time").text = row["timestamp"].isoformat() + "Z"

        # Add distance if available
        if not pd.isna(row["distance"]):
            ET.SubElement(trackpoint, "DistanceMeters").text = str(row["distance"])

        # Add heart rate if available
        if not pd.isna(row["heart_rate"]):
            heart_rate_element = ET.SubElement(trackpoint, "HeartRateBpm")
            ET.SubElement(heart_rate_element, "Value").text = str(int(row["heart_rate"]))

    # Convert XML tree to string
    tree = ET.ElementTree(tcx)
    tree.write(output_file, encoding="utf-8", xml_declaration=True)
    
    print(f"TCX file saved: {output_file}")

def main():
    df = load_fit(file)

    end = detect_stop(df)
    
    trimmed_run = trim(end, df)

    convert_to_tcx(trimmed_run, "trimmed_run.tcx")

