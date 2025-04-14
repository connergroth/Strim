import pandas as pd
import logging
import numpy as np
from datetime import datetime, timedelta

# Configure logging
logger = logging.getLogger(__name__)

def process_streams_data(stream_data, activity_metadata, corrected_distance=None):
    """
    Process Strava streams data: detect stops, trim data, and return trimmed metrics.
    
    Args:
        stream_data (dict/list/str): Stream data from Strava API in various formats
        activity_metadata (dict): Activity metadata from Strava API
        corrected_distance (float, optional): New distance in meters
        
    Returns:
        dict: Trimmed activity metrics
    """
    try:
        logger.info("Processing streams data")
        
        # Convert stream data to DataFrame
        df = streams_to_dataframe(stream_data)
        
        # More robust empty DataFrame check
        if df is None or df.empty or len(df) == 0:
            logger.error("Failed to convert streams to DataFrame or DataFrame is empty")
            # Log more details about the stream data for debugging
            if isinstance(stream_data, dict):
                logger.error(f"Stream data has keys: {list(stream_data.keys())}")
            elif isinstance(stream_data, list):
                logger.error(f"Stream data is a list with {len(stream_data)} items")
            elif isinstance(stream_data, str):
                logger.error(f"Stream data is a string (first 100 chars): {stream_data[:100]}...")
            else:
                logger.error(f"Stream data is of type {type(stream_data)}")
            return None
        
        logger.info(f"Created DataFrame with columns: {list(df.columns)}")
        
        # Detect when the activity stops
        end_index = detect_stop_from_streams(df)
        if end_index is None:
            logger.warning("Could not detect stop point, using full activity")
            end_index = len(df) - 1
        
        # Trim the data
        trimmed_df = df.iloc[:end_index+1].copy()
        logger.info(f"Trimmed activity from {len(df)} to {len(trimmed_df)} points")
        
        # Build metrics for the trimmed activity
        metrics = build_trimmed_metrics(trimmed_df, activity_metadata, corrected_distance)
        
        return metrics
    except Exception as e:
        logger.error(f"Error processing streams data: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise

def process_strava_streams(stream_data):
    """
    Process Strava streams data to ensure it's in a consistent format.
    Handles both list format and dictionary format that the API might return.
    
    Args:
        stream_data: Stream data from Strava API
        
    Returns:
        list: List of stream objects with 'type' and 'data' keys
    """
    if isinstance(stream_data, list):
        # It's already in the right format (list of stream objects)
        # Just validate that each object has the expected structure
        processed_streams = []
        for stream in stream_data:
            if isinstance(stream, dict) and 'type' in stream and 'data' in stream:
                processed_streams.append(stream)
            else:
                app.logger.warning(f"Skipping malformed stream: {stream}")
        return processed_streams
    
    elif isinstance(stream_data, dict):
        # It's in the alternate format (dict with stream types as keys)
        # Convert to the list format
        processed_streams = []
        for stream_type, stream_data_obj in stream_data.items():
            if isinstance(stream_data_obj, dict) and 'data' in stream_data_obj:
                # If it's {"time": {"data": [...]}, "distance": {"data": [...]}}
                stream_obj = stream_data_obj.copy()
                stream_obj['type'] = stream_type
                processed_streams.append(stream_obj)
            else:
                # If it's {"time": [...], "distance": [...]}
                processed_streams.append({
                    'type': stream_type,
                    'data': stream_data_obj
                })
        return processed_streams
    
    elif isinstance(stream_data, str):
        # It might be a JSON string that wasn't parsed
        app.logger.warning("Stream data is a string, attempting to parse as JSON")
        try:
            parsed_data = json.loads(stream_data)
            return process_strava_streams(parsed_data)
        except json.JSONDecodeError:
            app.logger.error("Failed to parse stream data string as JSON")
            return []
    
    else:
        app.logger.error(f"Unrecognized stream data format: {type(stream_data)}")
        return []

def streams_to_dataframe(stream_data):
    """
    Convert Strava streams to a pandas DataFrame.
    
    Args:
        stream_data (list/dict/str): Stream data from Strava API in various formats
        
    Returns:
        pandas.DataFrame: DataFrame containing stream data
    """
    try:
        # Initialize an empty dictionary to store data for each stream type
        data_dict = {}
        
        # Log the stream data type for debugging
        logger.info(f"Stream data type: {type(stream_data)}")
        
        # Handle JSON string input
        if isinstance(stream_data, str):
            try:
                import json
                stream_data = json.loads(stream_data)
                logger.info(f"Parsed JSON string into: {type(stream_data)}")
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON string: {str(e)}")
                return None
        
        # Handle dictionary format (stream types as keys)
        # Format: {"time": {"data": [...]}, "distance": {"data": [...]}}
        if isinstance(stream_data, dict):
            logger.info(f"Processing stream data in dictionary format")
            # Log the available keys
            logger.info(f"Available stream keys: {list(stream_data.keys())}")
            
            for stream_type, stream_obj in stream_data.items():
                if isinstance(stream_obj, dict) and 'data' in stream_obj:
                    stream_data_points = stream_obj.get('data')
                    if stream_data_points:
                        logger.info(f"Found stream type: {stream_type} with {len(stream_data_points)} data points")
                        data_dict[stream_type] = stream_data_points
        
        # Handle list format (list of stream objects)
        # Format: [{"type": "time", "data": [...]}, {"type": "distance", "data": [...]}]
        elif isinstance(stream_data, list):
            logger.info(f"Processing stream data in list format")
            for stream_obj in stream_data:
                if isinstance(stream_obj, dict):
                    stream_type = stream_obj.get('type')
                    stream_data_points = stream_obj.get('data')
                    
                    if stream_type and stream_data_points:
                        logger.info(f"Found stream type: {stream_type} with {len(stream_data_points)} data points")
                        data_dict[stream_type] = stream_data_points
        else:
            logger.error(f"Unsupported stream data format: {type(stream_data)}")
            return None
            
        # Check if we have the distance stream (required)
        if 'distance' not in data_dict:
            logger.error("Required 'distance' stream not found")
            if isinstance(stream_data, dict):
                logger.error(f"Available keys: {list(stream_data.keys())}")
            return None
            
        # Create a DataFrame with all available streams
        # If some streams have different lengths, pandas will fill with NaN
        df = pd.DataFrame(data_dict)
        
        # Create a time index if time stream is available
        if 'time' in data_dict:
            df['time_seconds'] = df['time']
            
        # If latlng is available, split it into lat and lng columns
        if 'latlng' in df.columns:
            try:
                df['lat'] = df['latlng'].apply(lambda x: x[0] if isinstance(x, list) and len(x) >= 2 else None)
                df['lng'] = df['latlng'].apply(lambda x: x[1] if isinstance(x, list) and len(x) >= 2 else None)
                df.drop('latlng', axis=1, inplace=True)
            except Exception as e:
                logger.warning(f"Could not split latlng: {str(e)}")
        
        logger.info(f"Successfully created DataFrame with {len(df)} rows and {len(df.columns)} columns")
        return df
        
    except Exception as e:
        logger.error(f"Error converting streams to DataFrame: {str(e)}")
        # Log more details about the stream data for debugging
        if isinstance(stream_data, dict):
            logger.error(f"Stream data keys: {list(stream_data.keys())}")
            if 'distance' in stream_data and isinstance(stream_data['distance'], dict):
                logger.error(f"Distance stream structure: {list(stream_data['distance'].keys())}")
        return None

def detect_stop_from_streams(df, flat_tolerance=0.5, flat_window=10, min_duration=20):
    """
    Detect when the user stopped moving by analyzing distance and velocity streams.
    
    Args:
        df (pandas.DataFrame): DataFrame with stream data
        flat_tolerance (float): Tolerance for distance changes (in meters)
        flat_window (int): Number of consecutive flat points to detect stop
        min_duration (int): Minimum duration in seconds to consider as a stop
        
    Returns:
        int: Index where stop was detected, or None if no stop detected
    """
    try:
        logger.info("Analyzing streams for stop detection")
        
        # Check if we have the necessary data
        if 'distance' not in df.columns:
            logger.warning("No distance data available for stop detection")
            return None
            
        # Log the total activity data
        total_points = len(df)
        total_distance = df['distance'].max() if 'distance' in df.columns else 0
        total_time = df['time'].max() if 'time' in df.columns else 0
        
        logger.info(f"Activity data: {total_points} points, {total_distance:.2f}m, {total_time:.0f} seconds")
        
        # First, try to use velocity data if available (more reliable)
        if 'velocity_smooth' in df.columns:
            logger.info("Using velocity data for stop detection")
            
            # Mark very low velocity points as potential stops
            velocity_threshold = 0.3  # very slow pace, almost stopped
            df['is_stopped'] = df['velocity_smooth'] < velocity_threshold
            
            # Count consecutive stopped points
            consecutive_stopped = 0
            stop_index = None
            stop_indices = []
            
            for idx, row in df.iterrows():
                if row['is_stopped']:
                    consecutive_stopped += 1
                    if consecutive_stopped >= flat_window:
                        # Found a potential stop point
                        stop_index = idx - flat_window + 1
                        stop_indices.append((stop_index, consecutive_stopped))
                else:
                    consecutive_stopped = 0
            
            # If we found potential stops, analyze them
            if stop_indices:
                # Sort by position (earlier in activity first)
                stop_indices.sort(key=lambda x: x[0])
                
                # Calculate duration for each stop if time data is available
                stops_with_duration = []
                for idx, count in stop_indices:
                    if 'time' in df.columns:
                        start_time = df.loc[idx, 'time']
                        end_idx = min(idx + count, total_points - 1)
                        end_time = df.loc[end_idx, 'time']
                        duration = end_time - start_time
                        
                        # If it's a substantial stop, use it
                        if duration >= min_duration:
                            stops_with_duration.append((idx, duration))
                            logger.info(f"Found velocity-based stop at index {idx}, duration {duration:.1f}s, distance {df.loc[idx, 'distance']:.2f}m")
                
                # If we have substantial stops, use the first one
                if stops_with_duration:
                    stop_index = stops_with_duration[0][0]
                    logger.info(f"Selected stop at index {stop_index}, distance {df.loc[stop_index, 'distance']:.2f}m")
                    return stop_index
        
        # Fallback: Use distance changes to detect stops
        logger.info("Using distance changes for stop detection")
        
        # Calculate distance changes
        df_temp = df.copy()
        df_temp['distance_diff'] = df_temp['distance'].diff().fillna(0)
        
        # Mark points where distance didn't change significantly
        df_temp['is_flat'] = df_temp['distance_diff'].abs() <= flat_tolerance
        
        # Look for consecutive flat points
        consecutive_flat = 0
        stop_index = None
        
        for idx, row in df_temp.iterrows():
            if row['is_flat']:
                consecutive_flat += 1
                if consecutive_flat >= flat_window:
                    stop_index = idx - flat_window + 1
                    
                    # Check if this is a substantial stop (using time data if available)
                    if 'time' in df_temp.columns:
                        start_time = df_temp.loc[stop_index, 'time']
                        end_time = df_temp.loc[min(idx, total_points-1), 'time']
                        duration = end_time - start_time
                        
                        if duration >= min_duration:
                            logger.info(f"Detected substantial stop at index {stop_index}, distance {df.loc[stop_index, 'distance']:.2f}m, duration {duration:.1f}s")
                            return stop_index
            else:
                consecutive_flat = 0
                
        # If we have a potential stop but didn't return yet, check its significance
        if stop_index is not None:
            logger.info(f"Detected potential stop at index {stop_index}, distance {df.loc[stop_index, 'distance']:.2f}m")
            
            # Check what percentage of the activity this represents
            stop_distance = df.loc[stop_index, 'distance']
            stop_percentage = (stop_distance / total_distance) * 100 if total_distance > 0 else 0
            
            # If the stop occurs very early (less than 20% into the activity), it might be a false positive
            if stop_percentage < 20:
                logger.warning(f"Stop detected too early ({stop_percentage:.1f}% of activity), ignoring")
                return None
                
            return stop_index
        
        logger.info("No stop detected, using complete activity")
        return None
        
    except Exception as e:
        logger.error(f"Error detecting stop: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return None

def build_trimmed_metrics(df, activity_metadata, corrected_distance=None):
    """
    Build metrics for a trimmed activity with improved time handling.
    
    Args:
        df (pandas.DataFrame): Trimmed DataFrame with stream data
        activity_metadata (dict): Original activity metadata
        corrected_distance (float, optional): New distance in meters
        
    Returns:
        dict: Metrics for the trimmed activity
    """
    try:
        metrics = {}
        
        # Copy basic metadata
        metrics['name'] = activity_metadata.get('name', 'Activity')
        metrics['type'] = activity_metadata.get('type', 'Run')
        
        # Preserve the original start time
        metrics['start_date_local'] = activity_metadata.get('start_date_local')
        logger.info(f"Using original start time: {metrics['start_date_local']}")
        
        # Use original description as is, without adding "Trimmed with Strim"
        metrics['description'] = activity_metadata.get('description', '')
            
        # Copy additional metadata for preservation
        if 'gear_id' in activity_metadata:
            metrics['gear_id'] = activity_metadata.get('gear_id')
            
        if 'photos' in activity_metadata:
            metrics['photos'] = activity_metadata.get('photos')
            
        # Preserve the original activity ID for reference
        if 'id' in activity_metadata:
            metrics['original_activity_id'] = activity_metadata.get('id')
        
        # Extract metrics from the trimmed data
        if 'distance' in df.columns:
            max_distance = df['distance'].max()
            
            # Apply distance correction if provided
            if corrected_distance and corrected_distance > 0:
                metrics['distance'] = corrected_distance
                logger.info(f"Corrected distance from {max_distance}m to {corrected_distance}m")
            else:
                metrics['distance'] = max_distance
                logger.info(f"Using original distance: {max_distance}m")
        
        # Calculate elapsed time
        if 'time' in df.columns:
            # Use the actual time from the data stream
            trimmed_elapsed = int(df['time'].max())
            logger.info(f"Elapsed time from stream: {trimmed_elapsed} seconds")
            
            # Check if it's reasonable
            original_elapsed = activity_metadata.get('elapsed_time', 0)
            if trimmed_elapsed > 0 and trimmed_elapsed <= original_elapsed:
                metrics['elapsed_time'] = trimmed_elapsed
            else:
                # If time seems wrong, estimate based on distance
                logger.warning(f"Stream elapsed time {trimmed_elapsed}s may be incorrect (original: {original_elapsed}s)")
                
                # If we have corrected distance, estimate time proportionally
                if corrected_distance and 'distance' in df.columns:
                    original_distance = activity_metadata.get('distance', 0)
                    if original_distance > 0 and original_elapsed > 0:
                        distance_ratio = corrected_distance / original_distance
                        estimated_time = int(original_elapsed * distance_ratio)
                        metrics['elapsed_time'] = estimated_time
                        logger.info(f"Estimated elapsed time based on distance ratio: {estimated_time}s")
                    else:
                        metrics['elapsed_time'] = original_elapsed
                        logger.info(f"Using original elapsed time: {original_elapsed}s")
                else:
                    metrics['elapsed_time'] = original_elapsed
                    logger.info(f"Using original elapsed time: {original_elapsed}s")
        elif 'time_seconds' in df.columns:
            metrics['elapsed_time'] = int(df['time_seconds'].max())
            logger.info(f"Elapsed time: {metrics['elapsed_time']} seconds")
        else:
            # If no time stream is available, estimate from original
            original_elapsed = activity_metadata.get('elapsed_time', 0)
            
            if corrected_distance is not None:
                original_distance = activity_metadata.get('distance', 0)
                if original_distance > 0:
                    distance_ratio = corrected_distance / original_distance
                    metrics['elapsed_time'] = int(original_elapsed * distance_ratio)
                    logger.info(f"Estimated elapsed time: {metrics['elapsed_time']} seconds")
                else:
                    metrics['elapsed_time'] = original_elapsed
                    logger.warning(f"Using original elapsed time: {original_elapsed} seconds")
            else:
                metrics['elapsed_time'] = original_elapsed
                logger.warning(f"Using original elapsed time: {original_elapsed} seconds")
        
        # Copy additional metadata
        metrics['trainer'] = activity_metadata.get('trainer', False)
        metrics['commute'] = activity_metadata.get('commute', False)
        
        # Preserve additional metadata that Strava accepts
        for field in ['private', 'sport_type', 'workout_type', 'hide_from_home']:
            if field in activity_metadata:
                metrics[field] = activity_metadata[field]
        
        # Calculate average speeds, heart rate, etc. if available
        if 'heartrate' in df.columns:
            metrics['average_heartrate'] = float(df['heartrate'].mean())
        elif 'average_heartrate' in activity_metadata:
            metrics['average_heartrate'] = activity_metadata['average_heartrate']
        
        if 'cadence' in df.columns:
            metrics['average_cadence'] = float(df['cadence'].mean())
        elif 'average_cadence' in activity_metadata:
            metrics['average_cadence'] = activity_metadata['average_cadence']
        
        if 'velocity_smooth' in df.columns:
            metrics['average_speed'] = float(df['velocity_smooth'].mean())
        elif 'average_speed' in activity_metadata:
            metrics['average_speed'] = activity_metadata['average_speed']
            
        # Preserve elevation data if available
        if 'altitude' in df.columns:
            metrics['total_elevation_gain'] = max(0, df['altitude'].max() - df['altitude'].min())
        elif 'total_elevation_gain' in activity_metadata:
            # Scale elevation based on distance ratio
            original_distance = activity_metadata.get('distance', 0)
            if original_distance > 0:
                distance_ratio = metrics['distance'] / original_distance
                metrics['total_elevation_gain'] = activity_metadata['total_elevation_gain'] * distance_ratio
        
        logger.info(f"Built metrics for trimmed activity: {metrics['name']}")
        return metrics
    except Exception as e:
        logger.error(f"Error building metrics: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise

def estimate_trimmed_activity_metrics(activity_id, stream_data, activity_metadata, corrected_distance=None):
    """
    Main function to estimate metrics for a trimmed activity.
    
    Args:
        activity_id (str): Strava activity ID
        stream_data (list or str): Stream data from Strava API (can be a JSON string or already parsed data)
        activity_metadata (dict): Activity metadata from Strava API
        corrected_distance (float, optional): New distance in meters
        
    Returns:
        dict: Metrics for creating a new trimmed activity
    """
    try:
        logger.info(f"Processing activity {activity_id}")
        
        # If stream_data is a string, try to parse it as JSON
        if isinstance(stream_data, str):
            try:
                import json
                logger.info("Received stream_data as string, attempting to parse as JSON")
                # Log a sample of the stream data
                logger.info(f"Stream data sample (first 100 chars): {stream_data[:100]}...")
                stream_data = json.loads(stream_data)
                logger.info(f"Successfully parsed JSON into {type(stream_data)}")
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse stream_data as JSON: {str(e)}")
                return None
        
        # Process the streams data
        metrics = process_streams_data(stream_data, activity_metadata, corrected_distance)
        
        if not metrics:
            logger.error("Failed to generate metrics for trimmed activity")
            return None
        
        return metrics
    except Exception as e:
        logger.error(f"Error estimating trimmed activity metrics: {str(e)}")
        logger.error(traceback.format_exc())  # Log the full traceback for debugging
        raise

def cleanup_activity(activity_id, token, original_name, original_description=None):
    """
    Clean up the activity by restoring original name and description.
    
    Args:
        activity_id (str): Strava activity ID
        token (str): Strava access token
        original_name (str): Original activity name to restore
        original_description (str, optional): Original description to restore
        
    Returns:
        bool: True if successful, False otherwise
    """
    import requests
    import logging
    import json
    
    logger = logging.getLogger(__name__)
    
    try:
        # Prepare the request URL
        url = f"https://www.strava.com/api/v3/activities/{activity_id}"
        
        # Set up headers
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        # Prepare the payload with clean name
        payload = {
            "name": original_name
        }
        
        # Add description if provided
        if original_description is not None:
            payload["description"] = original_description
        
        logger.info(f"Cleaning up activity {activity_id} - restoring original name")
        
        # Send the update request
        response = requests.put(url, headers=headers, data=json.dumps(payload))
        
        # Check if the request was successful
        if response.status_code == 200:
            logger.info(f"Successfully cleaned up activity {activity_id}")
            return True
        else:
            logger.error(f"Failed to clean up activity: {response.status_code} {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"Error cleaning up activity: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return False