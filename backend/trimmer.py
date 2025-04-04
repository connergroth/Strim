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

def detect_stop_from_streams(df, flat_tolerance=1.0, flat_window=5, min_duration=30):
    """
    Detect when the user stopped moving by analyzing distance stream.
    
    Args:
        df (pandas.DataFrame): DataFrame with stream data
        flat_tolerance (float): Tolerance for distance changes (in meters)
        flat_window (int): Number of consecutive flat points to detect stop
        min_duration (int): Minimum duration in seconds to consider as a stop
        
    Returns:
        int: Index where stop was detected, or None if no stop detected
    """
    try:
        if 'distance' not in df.columns:
            logger.warning("No distance data available for stop detection")
            return None
        
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
                    break
            else:
                consecutive_flat = 0
        
        if stop_index is not None:
            logger.info(f"Detected stop at index {stop_index}, distance {df.loc[stop_index, 'distance']:.2f}m")
            return stop_index
        
        # Alternative method: find a significant stop in the activity
        # Look for places where the distance doesn't change for a while
        flat_regions = []
        current_flat = None
        
        for idx, row in df_temp.iterrows():
            if row['is_flat']:
                if current_flat is None:
                    current_flat = {'start': idx, 'count': 1}
                else:
                    current_flat['count'] += 1
            else:
                if current_flat is not None and current_flat['count'] >= 3:  # At least 3 points of no movement
                    # Calculate duration of the flat region if time data is available
                    if 'time' in df_temp.columns:
                        start_time = df_temp.loc[current_flat['start'], 'time']
                        end_time = df_temp.loc[idx-1, 'time']
                        duration = end_time - start_time
                        current_flat['duration'] = duration
                    elif 'time_seconds' in df_temp.columns:
                        start_time = df_temp.loc[current_flat['start'], 'time_seconds']
                        end_time = df_temp.loc[idx-1, 'time_seconds']
                        duration = end_time - start_time
                        current_flat['duration'] = duration
                    else:
                        current_flat['duration'] = current_flat['count'] * 1  # Assume 1 second per data point if no time data
                        
                    flat_regions.append(current_flat)
                current_flat = None
        
        # Add the last region if it's flat
        if current_flat is not None and current_flat['count'] >= 3:
            # Calculate duration for the last flat region
            if 'time' in df_temp.columns:
                start_time = df_temp.loc[current_flat['start'], 'time']
                end_time = df_temp.loc[df_temp.index[-1], 'time']
                duration = end_time - start_time
                current_flat['duration'] = duration
            elif 'time_seconds' in df_temp.columns:
                start_time = df_temp.loc[current_flat['start'], 'time_seconds']
                end_time = df_temp.loc[df_temp.index[-1], 'time_seconds']
                duration = end_time - start_time
                current_flat['duration'] = duration
            else:
                current_flat['duration'] = current_flat['count'] * 1
                
            flat_regions.append(current_flat)
        
        # Filter regions by minimum duration
        significant_stops = [region for region in flat_regions if region.get('duration', 0) >= min_duration]
        
        # If we have significant stops, sort by position in the activity (prioritize earlier stops)
        if significant_stops:
            # Sort by position (start index) to find the first significant stop
            significant_stops.sort(key=lambda x: x['start'])
            stop_index = significant_stops[0]['start']
            logger.info(f"Detected significant stop at index {stop_index}, duration: {significant_stops[0].get('duration', 'unknown')} seconds")
            return stop_index
            
        # If no significant stops found, sort all flat regions by length (longest first)
        if flat_regions:
            flat_regions.sort(key=lambda x: x['count'], reverse=True)
            stop_index = flat_regions[0]['start']
            logger.info(f"Detected flat region at index {stop_index}, with {flat_regions[0]['count']} points")
            return stop_index
        
        logger.info("No stop detected, using complete activity")
        return None
    except Exception as e:
        logger.error(f"Error detecting stop: {str(e)}")
        return None

def build_trimmed_metrics(df, activity_metadata, corrected_distance=None):
    """
    Build metrics for a trimmed activity.
    
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
        metrics['name'] = activity_metadata.get('name', 'Trimmed Activity')
        metrics['type'] = activity_metadata.get('type', 'Run')
        metrics['start_date_local'] = activity_metadata.get('start_date_local')
        
        # Preserve original description if it exists, otherwise create new one
        original_description = activity_metadata.get('description', '')
        if original_description:
            metrics['description'] = f"{original_description}\n\n(Trimmed with Strim - Stops removed)"
        else:
            metrics['description'] = 'Trimmed with Strim - Stops removed'
            
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
            metrics['elapsed_time'] = int(df['time'].max())
            logger.info(f"Elapsed time: {metrics['elapsed_time']} seconds")
        elif 'time_seconds' in df.columns:
            metrics['elapsed_time'] = int(df['time_seconds'].max())
            logger.info(f"Elapsed time: {metrics['elapsed_time']} seconds")
        else:
            # If no time stream is available, estimate from original
            original_elapsed = activity_metadata.get('elapsed_time', 0)
            original_distance = activity_metadata.get('distance', 0)
            
            if original_distance > 0:
                distance_ratio = metrics['distance'] / original_distance
                metrics['elapsed_time'] = int(original_elapsed * distance_ratio)
                logger.info(f"Estimated elapsed time: {metrics['elapsed_time']} seconds")
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