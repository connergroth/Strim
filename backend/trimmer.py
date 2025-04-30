import pandas as pd
import logging
import numpy as np
import traceback
from datetime import datetime, timedelta
import json
import re
import math
from scipy.signal import find_peaks

# Setup logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def streams_to_dataframe(stream_data):
    """
    Convert Strava API stream data to a pandas DataFrame.
    
    Args:
        stream_data (dict): Stream data from Strava API
        
    Returns:
        pandas.DataFrame: DataFrame with all stream data combined
    """
    try:
        logger.info("Converting stream data to DataFrame")
        
        # Handle different input formats
        if isinstance(stream_data, str):
            try:
                stream_data = json.loads(stream_data)
            except Exception as e:
                logger.error(f"Failed to parse stream data JSON: {str(e)}")
                return None
                
        # Handle empty or invalid data
        if not stream_data:
            logger.error("Empty or None stream data provided")
            return None
            
        # Check if stream_data is a dict
        if isinstance(stream_data, dict):
            # Modern Strava API returns key_by_type=true format
            all_data = {}
            
            # Extract each stream type
            for stream_type, stream_obj in stream_data.items():
                if isinstance(stream_obj, dict) and 'data' in stream_obj:
                    all_data[stream_type] = stream_obj['data']
                    logger.info(f"Found stream: {stream_type} with {len(stream_obj['data'])} points")
                    
            # If we have any streams, convert to DataFrame
            if all_data:
                # Find the length of each stream
                stream_lengths = {k: len(v) for k, v in all_data.items()}
                logger.info(f"Stream lengths: {stream_lengths}")
                
                # Create DataFrame
                df = pd.DataFrame(all_data)
                logger.info(f"Created DataFrame with shape {df.shape}")
                return df
            else:
                logger.error("No valid streams found in data")
                return None
                
        # Handle list format (older API)
        elif isinstance(stream_data, list):
            all_data = {}
            
            for stream in stream_data:
                if isinstance(stream, dict) and 'type' in stream and 'data' in stream:
                    stream_type = stream['type']
                    all_data[stream_type] = stream['data']
                    logger.info(f"Found stream: {stream_type} with {len(stream['data'])} points")
            
            if all_data:
                df = pd.DataFrame(all_data)
                logger.info(f"Created DataFrame with shape {df.shape}")
                return df
            else:
                logger.error("No valid streams found in list data")
                return None
        else:
            logger.error(f"Unsupported stream data type: {type(stream_data)}")
            return None
            
    except Exception as e:
        logger.error(f"Error converting streams to DataFrame: {str(e)}")
        logger.error(traceback.format_exc())
        return None

def process_streams_data(stream_data, activity_metadata, corrected_distance=None, manual_trim_points=None):
    """
    Process Strava streams data: detect stops, trim data, and return trimmed metrics.
    
    Args:
        stream_data (dict/list/str): Stream data from Strava API in various formats
        activity_metadata (dict): Activity metadata from Strava API
        corrected_distance (float, optional): New distance in meters
        manual_trim_points (dict, optional): Manual trim points from user with 'start_time' and 'end_time'
        
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
        
        # Get activity type (default to Run)
        activity_type = activity_metadata.get('type', 'Run')
        logger.info(f"Processing activity of type: {activity_type}")
        
        # Determine end index for trimming
        end_index = None
        
        # If manual trim points are provided, use those instead of auto-detection
        if manual_trim_points and 'time' in df.columns:
            logger.info("Using manual trim points")
            start_time = manual_trim_points.get('start_time')
            end_time = manual_trim_points.get('end_time')
            
            if start_time is not None and end_time is not None:
                # Find the closest indices to the provided times
                time_array = df['time'].values
                
                # If start time is provided, find the closest index
                if start_time > 0:
                    # Find closest index to start_time
                    start_index = find_closest_index(time_array, start_time)
                    logger.info(f"Manual start time {start_time}s maps to index {start_index}")
                    
                    # Only trim from this point if it's after the beginning
                    if start_index > 0:
                        # Create a new DataFrame starting from this point
                        df = df.iloc[start_index:].copy()
                        df['time'] = df['time'] - df['time'].iloc[0]  # Reset time to start from 0
                        logger.info(f"Trimmed beginning from {start_index} to 0, new length: {len(df)}")
                
                # Find the closest index to end_time
                adjusted_end_time = end_time - (start_time if start_time > 0 else 0)
                end_index = find_closest_index(df['time'].values, adjusted_end_time)
                logger.info(f"Manual end time {end_time}s (adjusted to {adjusted_end_time}s) maps to index {end_index}")
            else:
                logger.warning("Incomplete manual trim points provided, falling back to auto-detection")
        
        # If end_index wasn't set by manual trim points, use auto-detection
        if end_index is None:
            # For running activities, use run-specific detection
            if activity_type.lower() in ['run', 'running']:
                end_index = detect_run_stop(df, activity_metadata)
            else:
                # For other activities, use the original algorithm
                end_index = detect_stop_from_streams(df)
                
            if end_index is None:
                logger.warning("Could not detect stop point, using full activity")
                end_index = len(df) - 1
        
        # Trim the data
        trimmed_df = df.iloc[:end_index+1].copy()
        logger.info(f"Trimmed activity from {len(df)} to {len(trimmed_df)} points")
        
        # Validate the trimming
        valid_trimming = validate_run_trimming(df, trimmed_df, activity_metadata)
        if not valid_trimming:
            logger.warning("Trimming validation failed, using full activity")
            trimmed_df = df.copy()
        
        # Build metrics for the trimmed activity
        metrics = build_trimmed_metrics(trimmed_df, activity_metadata, corrected_distance)
        
        return metrics
    except Exception as e:
        logger.error(f"Error processing streams data: {str(e)}")
        logger.error(traceback.format_exc())
        raise

def get_stop_detection_parameters(activity_type):
    """
    Get appropriate stop detection parameters based on activity type.
    
    Args:
        activity_type (str): Type of activity (run, ride, swim, etc.)
        
    Returns:
        dict: Parameters for stop detection
    """
    # Default parameters
    params = {
        'flat_tolerance': 0.5,  # meters
        'flat_window': 10,      # points
        'min_duration': 20,     # seconds
        'velocity_threshold': 0.3,  # m/s (about 1 km/h)
        'early_stop_percentage': 20,  # %
        'minimum_significant_distance': 100  # meters
    }
    
    # Adjust based on activity type
    if activity_type in ['run', 'running']:
        # For running, use slightly stricter parameters
        params['velocity_threshold'] = 0.25  # m/s (slower threshold for running)
        params['min_duration'] = 30  # seconds (longer min duration for running)
        params['minimum_significant_distance'] = 200  # meters
    elif activity_type in ['ride', 'cycling', 'biking']:
        # For cycling, use more relaxed velocity threshold
        params['velocity_threshold'] = 0.5  # m/s (cycling typically has higher speed)
        params['flat_tolerance'] = 1.0  # meters (more tolerance for cycling GPS)
        params['minimum_significant_distance'] = 300  # meters
    elif activity_type in ['swim', 'swimming']:
        # For swimming, use stricter parameters due to pool laps
        params['velocity_threshold'] = 0.1  # m/s 
        params['min_duration'] = 15  # seconds
        params['flat_window'] = 8  # points
        params['minimum_significant_distance'] = 50  # meters
    elif activity_type in ['hike', 'hiking', 'walk', 'walking']:
        # For hiking/walking, use relaxed parameters
        params['velocity_threshold'] = 0.2  # m/s
        params['min_duration'] = 40  # seconds (hikers might pause briefly)
        params['early_stop_percentage'] = 30  # % (more tolerance for early stops)
        params['minimum_significant_distance'] = 150  # meters
        
    logger.info(f"Using stop detection parameters for activity type '{activity_type}': {params}")
    return params

def validate_trimming(original_df, trimmed_df, activity_metadata):
    """
    Validate that trimming hasn't cut off too much or too little of the activity.
    
    Args:
        original_df (pandas.DataFrame): Original activity data
        trimmed_df (pandas.DataFrame): Trimmed activity data
        activity_metadata (dict): Original activity metadata
    """
    if len(trimmed_df) == 0:
        logger.error("Trimming resulted in empty data - will use full activity instead")
        return False
        
    # Calculate percentages of data retained
    percent_points = (len(trimmed_df) / len(original_df)) * 100
    
    if 'distance' in trimmed_df.columns and 'distance' in original_df.columns:
        original_distance = original_df['distance'].max()
        trimmed_distance = trimmed_df['distance'].max()
        percent_distance = (trimmed_distance / original_distance) * 100
        
        logger.info(f"Trimming stats: {percent_points:.1f}% of points, {percent_distance:.1f}% of distance")
        
        # Warn if trimming cut off too much data (less than 50% distance remaining)
        if percent_distance < 50:
            logger.warning(f"Aggressive trimming detected: only {percent_distance:.1f}% of distance remains")
            
            # If extremely aggressive (less than 30%), abort trimming
            if percent_distance < 30:
                logger.error("Trimming cut off too much data - will use full activity instead")
                return False
    else:
        logger.info(f"Trimming stats: {percent_points:.1f}% of points")
    
    # Ensure minimum activity length
    if 'time' in trimmed_df.columns:
        trimmed_time = trimmed_df['time'].max()
        if trimmed_time < 60:  # Less than 1 minute
            logger.warning(f"Trimmed activity is very short: {trimmed_time:.0f} seconds")
            
            # If less than 30 seconds, it's likely invalid
            if trimmed_time < 30:
                logger.error("Trimmed activity is too short - will use full activity instead")
                return False
    
    return True

def detect_stop_from_streams(df, flat_tolerance=0.5, flat_window=10, min_duration=20, 
                             velocity_threshold=0.3, early_stop_percentage=20,
                             minimum_significant_distance=100):
    """
    Detect when the user stopped moving by analyzing distance and velocity streams.
    
    Args:
        df (pandas.DataFrame): DataFrame with stream data
        flat_tolerance (float): Tolerance for distance changes (in meters)
        flat_window (int): Number of consecutive flat points to detect stop
        min_duration (int): Minimum duration in seconds to consider as a stop
        velocity_threshold (float): Threshold below which velocity is considered as stopped
        early_stop_percentage (float): Percentage of total distance below which a stop is considered too early
        minimum_significant_distance (float): Minimum distance in meters for a stop to be considered significant
        
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
        
        # Store all potential stops for evaluation
        potential_stops = []
        
        # First, try to use velocity data if available (more reliable)
        if 'velocity_smooth' in df.columns:
            logger.info(f"Using velocity data for stop detection (threshold: {velocity_threshold} m/s)")
            
            # Mark very low velocity points as potential stops
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
                        
                        # If it's a substantial stop, record it
                        if duration >= min_duration:
                            stop_distance = df.loc[idx, 'distance']
                            stops_with_duration.append({
                                'index': idx,
                                'duration': duration,
                                'distance': stop_distance,
                                'distance_percentage': (stop_distance / total_distance) * 100 if total_distance > 0 else 0,
                                'method': 'velocity'
                            })
                            logger.info(f"Found velocity-based stop at index {idx}, duration {duration:.1f}s, distance {stop_distance:.2f}m")
                
                # Add these to our potential stops
                potential_stops.extend(stops_with_duration)
        
        # Next: Use distance changes to detect stops (as another method)
        logger.info(f"Using distance changes for stop detection (tolerance: {flat_tolerance} m)")
        
        # Calculate distance changes
        df_temp = df.copy()
        df_temp['distance_diff'] = df_temp['distance'].diff().fillna(0)
        
        # Mark points where distance didn't change significantly
        df_temp['is_flat'] = df_temp['distance_diff'].abs() <= flat_tolerance
        
        # Look for consecutive flat points
        consecutive_flat = 0
        distance_stops = []
        
        for idx, row in df_temp.iterrows():
            if row['is_flat']:
                consecutive_flat += 1
                if consecutive_flat >= flat_window:
                    flat_stop_index = idx - flat_window + 1
                    
                    # Check if this is a substantial stop (using time data if available)
                    if 'time' in df_temp.columns:
                        start_time = df_temp.loc[flat_stop_index, 'time']
                        end_time = df_temp.loc[min(idx, total_points-1), 'time']
                        duration = end_time - start_time
                        
                        if duration >= min_duration:
                            stop_distance = df.loc[flat_stop_index, 'distance']
                            distance_stops.append({
                                'index': flat_stop_index,
                                'duration': duration,
                                'distance': stop_distance,
                                'distance_percentage': (stop_distance / total_distance) * 100 if total_distance > 0 else 0,
                                'method': 'distance'
                            })
                            logger.info(f"Found distance-based stop at index {flat_stop_index}, duration {duration:.1f}s, distance {stop_distance:.2f}m")
            else:
                consecutive_flat = 0
        
        # Add distance-based stops to potential stops
        potential_stops.extend(distance_stops)
        
        # If we have no potential stops, return None
        if not potential_stops:
            logger.info("No stops detected, using complete activity")
            return None
            
        # Sort all potential stops by distance
        potential_stops.sort(key=lambda x: x['distance'])
        
        # Filter out stops that occur too early
        filtered_stops = [stop for stop in potential_stops 
                         if stop['distance_percentage'] >= early_stop_percentage and
                            stop['distance'] >= minimum_significant_distance]
        
        if not filtered_stops:
            logger.info(f"All detected stops were too early or insignificant (< {early_stop_percentage}% of activity or < {minimum_significant_distance}m)")
            return None
        
        # From the remaining stops, select the best one
        # We'll use the first significant stop as the primary criteria
        selected_stop = filtered_stops[0]
        
        # If we have multiple significant stops close together, prefer the one that's more definitive
        if len(filtered_stops) > 1:
            # If two stops are close together (within 10% of total distance), prefer the one with longer duration
            if abs(filtered_stops[0]['distance'] - filtered_stops[1]['distance']) < (total_distance * 0.1):
                if filtered_stops[1]['duration'] > filtered_stops[0]['duration'] * 1.5:  # Second stop has 50% longer duration
                    selected_stop = filtered_stops[1]
                    logger.info(f"Selected second stop due to longer duration: {selected_stop['duration']:.1f}s vs {filtered_stops[0]['duration']:.1f}s")
        
        logger.info(f"Selected stop at index {selected_stop['index']}, distance {selected_stop['distance']:.2f}m, "
                   f"which is {selected_stop['distance_percentage']:.1f}% into the activity, duration {selected_stop['duration']:.1f}s")
        
        return selected_stop['index']
        
    except Exception as e:
        logger.error(f"Error detecting stop: {str(e)}")
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
        
        # Calculate and preserve velocity data
        if 'velocity_smooth' in df.columns:
            # Calculate average speed for the activity metadata
            metrics['average_speed'] = float(df['velocity_smooth'].mean())
            
            # Store the actual velocity data points for use in file creation
            metrics['velocity_data'] = df['velocity_smooth'].tolist()
            logger.info(f"Preserved {len(metrics['velocity_data'])} velocity data points for graphs")
        elif 'average_speed' in activity_metadata:
            metrics['average_speed'] = activity_metadata['average_speed']
            
        # Preserve elevation data if available
        if 'altitude' in df.columns:
            metrics['total_elevation_gain'] = max(0, df['altitude'].max() - df['altitude'].min())
            # Also preserve the altitude data
            metrics['altitude_data'] = df['altitude'].tolist()
            logger.info(f"Preserved {len(metrics['altitude_data'])} altitude data points")
        elif 'total_elevation_gain' in activity_metadata:
            # Scale elevation based on distance ratio
            original_distance = activity_metadata.get('distance', 0)
            if original_distance > 0:
                distance_ratio = metrics['distance'] / original_distance
                metrics['total_elevation_gain'] = activity_metadata['total_elevation_gain'] * distance_ratio
        
        # Store time and distance points as well to ensure we have complete data
        if 'time' in df.columns:
            metrics['time_data'] = df['time'].tolist()
        if 'distance' in df.columns:
            metrics['distance_data'] = df['distance'].tolist()
        
        logger.info(f"Built metrics for trimmed activity: {metrics['name']}")
        return metrics
    except Exception as e:
        logger.error(f"Error building metrics: {str(e)}")
        logger.error(traceback.format_exc())
        raise

def estimate_trimmed_activity_metrics(activity_id, stream_data, activity_metadata, corrected_distance=None, options=None):
    """
    Main function to estimate metrics for a trimmed activity.
    
    Args:
        activity_id (str): Strava activity ID
        stream_data (list or str): Stream data from Strava API (can be a JSON string or already parsed data)
        activity_metadata (dict): Activity metadata from Strava API
        corrected_distance (float, optional): New distance in meters
        options (dict, optional): Additional options
            - manual_trim_points (dict): Manual trim points with 'start_time' and 'end_time' values
        
    Returns:
        dict: Metrics for creating a new trimmed activity
    """
    try:
        logger.info(f"Processing activity {activity_id}")
        
        # Initialize options if None
        if options is None:
            options = {}
        
        # Get manual trim points if provided
        manual_trim_points = options.get('manual_trim_points', None)
        if manual_trim_points:
            logger.info(f"Using manual trim points: {manual_trim_points}")
        
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
        metrics = process_streams_data(stream_data, activity_metadata, corrected_distance, manual_trim_points)
        
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
        logger.error(traceback.format_exc())
        return False

def detect_run_stop(df, activity_metadata):
    """
    Enhanced stop detection algorithm specifically optimized for running activities.
    Handles interval training and better distinguishes between actual stops and brief pauses.
    
    Args:
        df (pandas.DataFrame): DataFrame with stream data
        activity_metadata (dict): Activity metadata
        
    Returns:
        int: Index where stop was detected, or None if no stop detected
    """
    try:
        logger.info("Using run-optimized algorithm for stop detection")
        
        # Check if we have the necessary data
        if 'distance' not in df.columns:
            logger.warning("No distance data available for stop detection")
            return None
            
        # Log the total activity data
        total_points = len(df)
        total_distance = df['distance'].max() if 'distance' in df.columns else 0
        total_time = df['time'].max() if 'time' in df.columns else 0
        
        logger.info(f"Run data: {total_points} points, {total_distance:.2f}m, {total_time:.0f} seconds")
        
        # Parameters specifically tuned for running
        velocity_threshold = 0.25  # m/s (slower threshold for running, ~0.9 km/h)
        flat_tolerance = 0.4  # meters (GPS accuracy for running)
        flat_window = 8  # points (more sensitive for running)
        min_duration = 25  # seconds (longer stops for running)
        min_significant_distance = 250  # meters (minimum distance before considering a stop valid)
        cooldown_distance_pct = 25  # % (percentage of total distance that might be cooldown)
        
        # Store all potential stops for evaluation
        potential_stops = []
        
        # First, try to use velocity data if available (more reliable)
        if 'velocity_smooth' in df.columns:
            logger.info("Using velocity data for running stop detection")
            
            # Mark very low velocity points as potential stops
            df['is_stopped'] = df['velocity_smooth'] < velocity_threshold
            
            # Look for clusters of stopped points that might represent a real stop
            consecutive_stopped = 0
            
            for idx, row in df.iterrows():
                if row['is_stopped']:
                    consecutive_stopped += 1
                    if consecutive_stopped >= flat_window:
                        # Found a potential stop point
                        stop_idx = idx - flat_window + 1
                        
                        # Calculate duration if time data is available
                        if 'time' in df.columns:
                            # Get the time at this point
                            stop_time = df.loc[stop_idx, 'time']
                            
                            # Find the end of this stop segment (when velocity increases again)
                            end_of_stop_idx = None
                            for i in range(stop_idx + 1, len(df)):
                                if not df.loc[i, 'is_stopped']:
                                    end_of_stop_idx = i - 1
                                    break
                            
                            # If we couldn't find the end, it means the runner stopped until the end
                            if end_of_stop_idx is None:
                                end_of_stop_idx = len(df) - 1
                                
                            # Calculate the duration of this stop
                            stop_end_time = df.loc[end_of_stop_idx, 'time']
                            duration = stop_end_time - stop_time
                            
                            # If it's a substantial stop, add it to potential stops
                            if duration >= min_duration:
                                stop_distance = df.loc[stop_idx, 'distance']
                                distance_pct = (stop_distance / total_distance) * 100 if total_distance > 0 else 0
                                potential_stops.append({
                                    'index': stop_idx,
                                    'duration': duration,
                                    'distance': stop_distance,
                                    'distance_pct': distance_pct,
                                    'method': 'velocity'
                                })
                                logger.info(f"Found velocity-based stop: idx={stop_idx}, "
                                           f"dist={stop_distance:.1f}m ({distance_pct:.1f}%), "
                                           f"duration={duration:.1f}s")
                            
                            # Skip ahead to avoid duplicate detections
                            idx = end_of_stop_idx
                else:
                    consecutive_stopped = 0
        
        # Also check for distance-based stopping (alternate detection method)
        df_temp = df.copy()
        df_temp['distance_diff'] = df_temp['distance'].diff().fillna(0)
        df_temp['is_flat'] = df_temp['distance_diff'].abs() <= flat_tolerance
        
        # Look for consecutive flat points
        consecutive_flat = 0
        
        for idx, row in df_temp.iterrows():
            if row['is_flat']:
                consecutive_flat += 1
                if consecutive_flat >= flat_window:
                    flat_stop_idx = idx - flat_window + 1
                    
                    # Calculate duration if time data is available
                    if 'time' in df_temp.columns:
                        # Find the end of this flat segment
                        end_of_flat_idx = None
                        for i in range(flat_stop_idx + 1, len(df_temp)):
                            if not df_temp.loc[i, 'is_flat']:
                                end_of_flat_idx = i - 1
                                break
                        
                        # If we couldn't find the end, it means the flat segment continues to the end
                        if end_of_flat_idx is None:
                            end_of_flat_idx = len(df_temp) - 1
                        
                        # Calculate duration
                        start_time = df_temp.loc[flat_stop_idx, 'time']
                        end_time = df_temp.loc[end_of_flat_idx, 'time']
                        duration = end_time - start_time
                        
                        if duration >= min_duration:
                            stop_distance = df.loc[flat_stop_idx, 'distance']
                            distance_pct = (stop_distance / total_distance) * 100 if total_distance > 0 else 0
                            potential_stops.append({
                                'index': flat_stop_idx,
                                'duration': duration,
                                'distance': stop_distance,
                                'distance_pct': distance_pct,
                                'method': 'distance'
                            })
                            logger.info(f"Found distance-based stop: idx={flat_stop_idx}, "
                                       f"dist={stop_distance:.1f}m ({distance_pct:.1f}%), "
                                       f"duration={duration:.1f}s")
                            
                            # Skip ahead
                            idx = end_of_flat_idx
            else:
                consecutive_flat = 0
        
        # If we don't have any potential stops, return None
        if not potential_stops:
            logger.info("No potential stops found in run")
            return None
            
        # Filter stops:
        # 1. Remove early stops (< min_significant_distance)
        # 2. Remove stops during interval training (brief pauses in the middle)
        # 3. Identify the most likely true stopping point
        
        # Sort by distance
        potential_stops.sort(key=lambda x: x['distance'])
        
        # Filter out stops that occur too early
        filtered_stops = [stop for stop in potential_stops if stop['distance'] >= min_significant_distance]
        
        if not filtered_stops:
            logger.info(f"All stops occurred too early (< {min_significant_distance}m)")
            return None
            
        # Detect typical interval training pattern
        # In interval training, there are usually brief stops followed by resuming at similar pace
        is_interval_training = False
        
        # Check for multiple stops with continued activity
        if len(filtered_stops) > 1:
            # Check if substantial activity occurs after multiple stops
            early_stops = [s for s in filtered_stops if s['distance_pct'] < 80]
            if len(early_stops) > 1:
                # Calculate the average time between stops
                if len(early_stops) >= 3:  # Need at least 3 to establish a pattern
                    stop_distances = [s['distance'] for s in early_stops]
                    intervals = [stop_distances[i+1] - stop_distances[i] for i in range(len(stop_distances)-1)]
                    avg_interval = sum(intervals) / len(intervals)
                    
                    # If intervals are relatively consistent, it's likely interval training
                    if all(abs(i - avg_interval) / avg_interval < 0.4 for i in intervals):
                        is_interval_training = True
                        logger.info(f"Detected interval training pattern with {len(early_stops)} intervals "
                                   f"averaging {avg_interval:.1f}m apart")
        
        # For interval training, look for the final stop (cooldown end)
        if is_interval_training:
            # For interval training, find the last stop in the cooldown section
            cooldown_start = total_distance * (1 - cooldown_distance_pct/100)
            cooldown_stops = [s for s in filtered_stops if s['distance'] >= cooldown_start]
            
            if cooldown_stops:
                # Use the longest duration stop in the cooldown section
                selected_stop = max(cooldown_stops, key=lambda x: x['duration'])
                logger.info(f"Selected cooldown stop at {selected_stop['distance_pct']:.1f}% of run "
                           f"with duration {selected_stop['duration']:.1f}s")
                return selected_stop['index']
            else:
                # If no cooldown stop found, use the last major stop
                selected_stop = filtered_stops[-1]
                logger.info(f"No cooldown identified, using last major stop at "
                           f"{selected_stop['distance_pct']:.1f}% of run")
                return selected_stop['index']
        
        # Not interval training - find the most significant stop
        # For regular runs, the most significant stop is usually:
        # 1. Has long duration
        # 2. Is closer to the end (finished run)
        # 3. Velocity drops to near zero
        
        # Score each stop based on heuristics
        for stop in filtered_stops:
            # Base score on duration (longer is better)
            duration_score = min(1.0, stop['duration'] / 120)  # 2 minutes or longer is max score
            
            # Position score (higher for stops toward the end but not at the very end)
            position_score = 0
            if stop['distance_pct'] > 80:  # Near the end (last 20%)
                position_score = 1.0
            elif stop['distance_pct'] > 60:  # Last 40%
                position_score = 0.8
            elif stop['distance_pct'] > 40:  # Middle
                position_score = 0.5
            else:  # First half
                position_score = 0.3
                
            # Method score (velocity-based detection is more reliable)
            method_score = 1.0 if stop['method'] == 'velocity' else 0.7
            
            # Calculate total score
            stop['score'] = (duration_score * 0.5) + (position_score * 0.3) + (method_score * 0.2)
            logger.info(f"Stop at {stop['distance_pct']:.1f}% scored {stop['score']:.2f} "
                       f"(duration={duration_score:.2f}, position={position_score:.2f}, method={method_score:.2f})")
        
        # Select the stop with the highest score
        selected_stop = max(filtered_stops, key=lambda x: x['score'])
        logger.info(f"Selected stop at index {selected_stop['index']}, "
                   f"distance {selected_stop['distance']:.2f}m ({selected_stop['distance_pct']:.1f}%), "
                   f"duration {selected_stop['duration']:.1f}s, score {selected_stop['score']:.2f}")
        
        return selected_stop['index']
        
    except Exception as e:
        logger.error(f"Error in run stop detection: {str(e)}")
        logger.error(traceback.format_exc())
        return None

def validate_run_trimming(original_df, trimmed_df, activity_metadata):
    """
    Validate that the trimming of a running activity is reasonable.
    Ensures we haven't cut off too much or too little of the run.
    
    Args:
        original_df (pandas.DataFrame): Original activity data
        trimmed_df (pandas.DataFrame): Trimmed activity data
        activity_metadata (dict): Original activity metadata
        
    Returns:
        bool: True if trimming is valid, False if not
    """
    if len(trimmed_df) == 0:
        logger.error("Trimming resulted in empty data - will use full activity")
        return False
        
    # Calculate percentages of data retained
    percent_points = (len(trimmed_df) / len(original_df)) * 100
    
    if 'distance' in trimmed_df.columns and 'distance' in original_df.columns:
        original_distance = original_df['distance'].max()
        trimmed_distance = trimmed_df['distance'].max()
        percent_distance = (trimmed_distance / original_distance) * 100
        
        logger.info(f"Run trimming stats: {percent_points:.1f}% of points, {percent_distance:.1f}% of distance")
        
        # For running, we typically don't want to cut off more than 25% of the activity
        # Unless the user has manually specified a much shorter distance
        if percent_distance < 75:
            logger.warning(f"Aggressive run trimming detected: only {percent_distance:.1f}% of distance remains")
            
            # For running, anything less than 70% remaining is likely too aggressive
            if percent_distance < 70:
                logger.error("Trimming cut off too much of the run - will use full activity")
                return False
    else:
        logger.info(f"Run trimming stats: {percent_points:.1f}% of points")
    
    # For runs, ensure a minimum activity length
    if 'time' in trimmed_df.columns:
        trimmed_time = trimmed_df['time'].max()
        if trimmed_time < 180:  # Less than 3 minutes
            logger.warning(f"Trimmed run is very short: {trimmed_time:.0f} seconds")
            
            # If less than 1 minute, it's likely invalid for a run
            if trimmed_time < 60:
                logger.error("Trimmed run is too short - will use full activity")
                return False
    
    # Check pace consistency before and after trimming
    if 'velocity_smooth' in original_df.columns and 'velocity_smooth' in trimmed_df.columns:
        # Calculate average pace for original and trimmed
        original_pace = original_df['velocity_smooth'].mean()
        trimmed_pace = trimmed_df['velocity_smooth'].mean()
        
        # Calculate the pace difference as a percentage
        pace_change_pct = abs(trimmed_pace - original_pace) / original_pace * 100
        
        # If pace changed dramatically (more than 30%), it might be incorrect trimming
        if pace_change_pct > 30:
            logger.warning(f"Pace changed dramatically after trimming: {pace_change_pct:.1f}% difference")
            
            # If extremely dramatic (more than 50%), reject the trimming
            if pace_change_pct > 50:
                logger.error("Pace change too dramatic - will use full activity")
                return False
    
    return True

def find_closest_index(array, value):
    """
    Find the index of the closest value in an array.
    
    Args:
        array (numpy.ndarray): Array of values
        value (float): Target value
        
    Returns:
        int: Index of the closest value
    """
    # Calculate absolute differences
    absolute_diff = np.abs(array - value)
    
    # Find index of minimum difference
    closest_index = absolute_diff.argmin()
    
    return closest_index