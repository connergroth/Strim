from fitparse import FitFile
import pandas as pd
import xml.etree.ElementTree as ET
import os
import logging

# Configure logging
logger = logging.getLogger(__name__)

UPLOAD_FOLDER = "uploads"

def load_fit(file_path):
    """
    Load a FIT file and convert it to a pandas DataFrame.
    
    Args:
        file_path (str): Path to the FIT file
        
    Returns:
        pandas.DataFrame: DataFrame containing the activity data
    """
    try:
        logger.info(f"Loading FIT file: {file_path}")
        
        if not os.path.exists(file_path):
            logger.error(f"FIT file does not exist: {file_path}")
            raise FileNotFoundError(f"File not found: {file_path}")
            
        fitFile = FitFile(file_path)
        records = []

        for record in fitFile.get_messages("record"):
            record_data = record.get_values()
            records.append({
                "timestamp": record_data.get("timestamp"),
                "distance": record_data.get("distance"),
                "heart_rate": record_data.get("heart_rate"),
                "position_lat": record_data.get("position_lat"),
                "position_long": record_data.get("position_long"),
                "altitude": record_data.get("altitude"),
                "speed": record_data.get("speed"),
                "cadence": record_data.get("cadence"),
            })
        
        df = pd.DataFrame(records)
        logger.info(f"Successfully loaded FIT file with {len(df)} records")
        return df
    except Exception as e:
        logger.error(f"Error loading FIT file: {str(e)}")
        raise

def detect_stop(df):
    """
    Detect when the activity stops (no distance change) and return the timestamp.
    
    Args:
        df (pandas.DataFrame): DataFrame containing the activity data
        
    Returns:
        datetime: Timestamp of the detected stop
    """
    try:
        if df.empty:
            logger.warning("Empty DataFrame provided to detect_stop")
            return None
            
        # Only keep rows with distance values
        df = df.dropna(subset=["distance"])
        
        if df.empty:
            logger.warning("No distance data found in activity")
            return None
            
        # Create a copy to avoid SettingWithCopyWarning
        df = df.copy()
        
        # Calculate distance differences between consecutive points
        df["distance_diff"] = df["distance"].diff()

        # Look for first instance where distance doesn't change
        for index, row in df.iterrows():
            if row["distance_diff"] == 0:
                logger.info(f"Stop detected at timestamp: {row['timestamp']}")
                return row["timestamp"]
        
        # If no stop is found, return the max timestamp
        logger.info("No stop detected, using max timestamp")
        return df["timestamp"].max()
    except Exception as e:
        logger.error(f"Error detecting stop: {str(e)}")
        raise

def trim(df, end_timestamp, corrected_distance=None):
    """
    Trim the activity data to the given end timestamp and optionally correct the distance.
    
    Args:
        df (pandas.DataFrame): DataFrame containing the activity data
        end_timestamp (datetime): Timestamp to trim the activity to
        corrected_distance (float, optional): New distance to scale the activity to
        
    Returns:
        pandas.DataFrame: Trimmed and optionally distance-corrected DataFrame
    """
    try:
        if df.empty:
            logger.warning("Empty DataFrame provided to trim")
            return df
            
        if end_timestamp is None:
            logger.warning("No end timestamp provided, returning original data")
            return df
            
        # Trim data to end timestamp
        trimmed_df = df[df["timestamp"] <= end_timestamp].copy()
        logger.info(f"Trimmed activity from {len(df)} to {len(trimmed_df)} records")
        
        # Apply distance correction if provided
        if corrected_distance and corrected_distance > 0:
            max_distance = trimmed_df["distance"].max()
            if max_distance > 0:  # Prevent division by zero
                distance_ratio = corrected_distance / max_distance
                trimmed_df["distance"] = trimmed_df["distance"] * distance_ratio
                logger.info(f"Corrected distance from {max_distance} to {corrected_distance}")
            else:
                logger.warning("Max distance is 0, could not apply distance correction")

        return trimmed_df
    except Exception as e:
        logger.error(f"Error trimming data: {str(e)}")
        raise

def convert_to_tcx(df, output_file, corrected_pace=None):
    """
    Convert the activity data to TCX format and save to a file.
    
    Args:
        df (pandas.DataFrame): DataFrame containing the activity data
        output_file (str): Path to save the TCX file
        corrected_pace (float, optional): New pace to include in the TCX file
        
    Returns:
        str: Path to the saved TCX file
    """
    try:
        if df.empty:
            logger.warning("Empty DataFrame provided to convert_to_tcx")
            raise ValueError("Cannot create TCX from empty data")
            
        # Create TCX structure
        tcx = ET.Element("TrainingCenterDatabase", {
            "xmlns": "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2",
            "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
            "xsi:schemaLocation": "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2 http://www.garmin.com/xmlschemas/TrainingCenterDatabasev2.xsd"
        })
        
        activities = ET.SubElement(tcx, "Activities")
        activity = ET.SubElement(activities, "Activity", Sport="Running")

        # Set activity start time
        start_time = df["timestamp"].iloc[0].isoformat() + "Z"
        ET.SubElement(activity, "Id").text = start_time

        # Create lap element
        lap = ET.SubElement(activity, "Lap", StartTime=start_time)
        
        # Calculate total time in seconds
        total_time = (df["timestamp"].max() - df["timestamp"].min()).total_seconds()
        ET.SubElement(lap, "TotalTimeSeconds").text = str(total_time)
        
        # Set distance
        max_distance = df["distance"].max()
        ET.SubElement(lap, "DistanceMeters").text = str(max_distance)

        # Set pace if provided
        if corrected_pace:
            pace_mps = (1 / corrected_pace) * 26.8224  # Convert min/mile to m/s
            ET.SubElement(lap, "AvgSpeed").text = str(pace_mps)

        # Create track element
        track = ET.SubElement(lap, "Track")

        # Add trackpoints
        for _, row in df.iterrows():
            trackpoint = ET.SubElement(track, "Trackpoint")
            ET.SubElement(trackpoint, "Time").text = row["timestamp"].isoformat() + "Z"

            # Add position if available
            if not pd.isna(row["position_lat"]) and not pd.isna(row["position_long"]):
                position = ET.SubElement(trackpoint, "Position")
                ET.SubElement(position, "LatitudeDegrees").text = str(row["position_lat"])
                ET.SubElement(position, "LongitudeDegrees").text = str(row["position_long"])

            # Add altitude if available
            if not pd.isna(row["altitude"]):
                ET.SubElement(trackpoint, "AltitudeMeters").text = str(row["altitude"])

            # Add distance if available
            if not pd.isna(row["distance"]):
                ET.SubElement(trackpoint, "DistanceMeters").text = str(row["distance"])

            # Add heart rate if available
            if not pd.isna(row["heart_rate"]):
                heart_rate_element = ET.SubElement(trackpoint, "HeartRateBpm")
                ET.SubElement(heart_rate_element, "Value").text = str(int(row["heart_rate"]))

            # Add cadence if available
            if not pd.isna(row["cadence"]):
                ET.SubElement(trackpoint, "Cadence").text = str(int(row["cadence"]))

        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_file) if os.path.dirname(output_file) else '.', exist_ok=True)
        
        # Write TCX file
        tree = ET.ElementTree(tcx)
        tree.write(output_file, encoding="utf-8", xml_declaration=True)
        logger.info(f"Successfully wrote TCX file to {output_file}")

        return output_file
    except Exception as e:
        logger.error(f"Error converting to TCX: {str(e)}")
        raise

def process_file(file_path, corrected_distance=None):
    """
    Process a FIT file: load it, detect stops, trim it, and convert to TCX.
    
    Args:
        file_path (str): Path to the FIT file
        corrected_distance (float, optional): New distance in meters
        
    Returns:
        str: Path to the generated TCX file
    """
    try:
        logger.info(f"Processing file: {file_path}")
        
        # Step 1: Load the FIT file
        df = load_fit(file_path)
        
        # Step 2: Detect when the activity stops
        end_timestamp = detect_stop(df)
        
        # Step 3: Trim the data
        trimmed_df = trim(df, end_timestamp, corrected_distance)
        
        # Step 4: Convert to TCX
        base_name = os.path.basename(file_path)
        trimmed_tcx = os.path.join(UPLOAD_FOLDER, f"trimmed_{base_name.replace('.fit', '.tcx')}")
        convert_to_tcx(trimmed_df, trimmed_tcx)
        
        logger.info(f"Successfully processed file, TCX saved at: {trimmed_tcx}")
        return trimmed_tcx
    except Exception as e:
        logger.error(f"Error processing file: {str(e)}")
        raise