"""Display Pupil Labs invisible video feed with eye-gaze and ArUco marker tracking

Based on the async demo from Pupil Labs documentation, https://pupil-labs-realtime-api.readthedocs.io/en/stable/examples/async.html 
"""

import asyncio
import contextlib
import typing as T
import cv2
import argparse, os
from datetime import datetime
import numpy as np
import json

from pupil_labs.realtime_api import (
    Device,
    Network,
    receive_gaze_data,
    receive_video_frames,
)

# Initialize ArUco detector (new API for OpenCV 4.7+)
# Using DICT_4X4_100 which supports 100 unique markers (you need ~20)
# For more markers, use DICT_5X5_250 or DICT_6X6_250
aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_100)
aruco_params = cv2.aruco.DetectorParameters()
aruco_detector = cv2.aruco.ArucoDetector(aruco_dict, aruco_params)

def load_markers_config(config_file='markers_a0.json'):
    """Load marker configuration from JSON file"""
    with open(config_file, 'r') as f:
        config = json.load(f)
    
    # Build 3D object points for each marker in the surface coordinate system
    # Origin is top-left corner of surface, Y axis points down, X axis points right
    marker_data = {}
    for marker in config['markers']:
        marker_id = marker['id']
        size_mm = marker['size']
        pos_x = marker['position']['x']
        pos_y = marker['position']['y']
        
        # Define the 4 corners of the marker in 3D (Z=0, planar surface)
        # Marker is centered at position
        half_size = size_mm / 2.0
        obj_points = np.array([
            [pos_x - half_size, pos_y - half_size, 0],  # Top-left
            [pos_x + half_size, pos_y - half_size, 0],  # Top-right
            [pos_x + half_size, pos_y + half_size, 0],  # Bottom-right
            [pos_x - half_size, pos_y + half_size, 0]   # Bottom-left
        ], dtype=np.float32)
        
        marker_data[marker_id] = obj_points
    
    # Define surface corners for drawing borders
    surface_corners_3d = np.array([
        [0, 0, 0],
        [config['surface']['width'], 0, 0],
        [config['surface']['width'], config['surface']['height'], 0],
        [0, config['surface']['height'], 0]
    ], dtype=np.float32)
    
    return marker_data, surface_corners_3d, config

# Load marker configuration at startup
marker_3d_points, surface_corners_3d, markers_config = load_markers_config()

async def runcam(record_video=None):
    
    async with Network() as network:
        dev_info = await network.wait_for_new_device(timeout_seconds=5)

    if dev_info is None:
        print("No device could be found! Abort")
        return

    async with Device.from_discovered_device(dev_info) as device:
        print(f"Getting status information from {device}")
        status = await device.get_status()
        sensor_gaze = status.direct_gaze_sensor()

        if not sensor_gaze.connected:
            print(f"Gaze sensor is not connected to {device}")
            return

        sensor_world = status.direct_world_sensor()

        if not sensor_world.connected:
            print(f"Scene camera is not connected to {device}")
            return


        restart_on_disconnect = True
        queue_video = asyncio.Queue()
        queue_gaze = asyncio.Queue()
        process_video = asyncio.create_task(
            enqueue_sensor_data(
                receive_video_frames(sensor_world.url, run_loop=restart_on_disconnect),
                queue_video,
            )
        )

        process_gaze = asyncio.create_task(
            enqueue_sensor_data(
                receive_gaze_data(sensor_gaze.url, run_loop=restart_on_disconnect),
                queue_gaze,
            )
        )

        try:
            await match_and_draw(queue_video, queue_gaze, record_video)

        finally:
            process_video.cancel()
            process_gaze.cancel()

async def enqueue_sensor_data(sensor: T.AsyncIterator, queue: asyncio.Queue) -> None:

    async for datum in sensor:
        try:
            queue.put_nowait((datum.datetime, datum))

        except asyncio.QueueFull:
            print(f"Queue is full, dropping {datum}")

async def match_and_draw(queue_video, queue_gaze, record_video=None):
    video_writer = None
    
    # Initialize video writer if recording video
    if record_video:
        # Will set up video writer after getting first frame to determine dimensions
        video_writer_initialized = False

    while True:
        video_datetime, video_frame = await get_most_recent_item(queue_video)
        _, gaze_datum = await get_closest_item(queue_gaze, video_datetime)
        bgr_buffer = video_frame.to_ndarray(format="bgr24")
        
        # Initialize video writer on first frame
        if record_video and not video_writer_initialized:
            height, width = bgr_buffer.shape[:2]
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            video_writer = cv2.VideoWriter(record_video, fourcc, 30.0, (width, height))
            video_writer_initialized = True
            print(f"Recording video to {record_video}")

        # Detect ArUco markers
        gray = cv2.cvtColor(bgr_buffer, cv2.COLOR_BGR2GRAY)
        corners, ids, rejected = aruco_detector.detectMarkers(gray)
        
        # Gaze point
        gaze_point = (int(gaze_datum.x), int(gaze_datum.y))
        looked_at_marker = None
        
        # Estimate surface pose if markers are detected
        surface_detected = False
        if ids is not None:
            # Collect 3D-2D point correspondences for markers defined in config
            obj_points_list = []
            img_points_list = []
            
            for i, marker_id in enumerate(ids.flatten()):
                if marker_id in marker_3d_points:
                    obj_points_list.append(marker_3d_points[marker_id])
                    img_points_list.append(corners[i][0])
            
            # Need at least one marker to estimate pose
            if len(obj_points_list) > 0:
                obj_points = np.vstack(obj_points_list)
                img_points = np.vstack(img_points_list)
                
                # Camera model for Pupil Labs Invisible scene camera
                # Wide-angle camera with significant distortion
                height, width = bgr_buffer.shape[:2]
                
                # Reduced focal length for wider FOV (empirically calibrated)
                # If surface appears 2x too large, halve the focal length
                focal_length = width * 0.577  # Adjusted for ~120° FOV
                
                camera_matrix = np.array([
                    [focal_length, 0, width / 2],
                    [0, focal_length, height / 2],
                    [0, 0, 1]
                ], dtype=np.float32)
                
                # Add radial distortion coefficients for wide-angle lens
                # k1 (barrel distortion), k2, p1, p2 (tangential), k3
                # Negative k1 for typical wide-angle barrel distortion
                dist_coeffs = np.array([[-0.2, 0.1, 0, 0, 0]], dtype=np.float32)
                
                # Solve PnP to get rotation and translation vectors
                success, rvec, tvec = cv2.solvePnP(obj_points, img_points, camera_matrix, dist_coeffs)
                
                if success:
                    surface_detected = True
                    
                    # Project surface corners to image
                    surface_corners_2d, _ = cv2.projectPoints(
                        surface_corners_3d, rvec, tvec, camera_matrix, dist_coeffs
                    )
                    surface_corners_2d = surface_corners_2d.reshape(-1, 2).astype(int)
                    
                    # Draw surface border
                    cv2.polylines(bgr_buffer, [surface_corners_2d], True, (0, 255, 255), 3)
                    
                    # Add corner labels
                    corner_labels = ['TL', 'TR', 'BR', 'BL']
                    for j, (corner, label) in enumerate(zip(surface_corners_2d, corner_labels)):
                        cv2.circle(bgr_buffer, tuple(corner), 8, (0, 255, 255), -1)
                        cv2.putText(bgr_buffer, label, tuple(corner + np.array([10, -10])),
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 2)
                    
                    # Project gaze point onto surface
                    # Convert rotation vector to matrix
                    R, _ = cv2.Rodrigues(rvec)
                    
                    # Undistort gaze point
                    gaze_undistorted = cv2.undistortPoints(
                        np.array([[gaze_point]], dtype=np.float32),
                        camera_matrix, dist_coeffs, P=camera_matrix
                    )[0][0]
                    
                    # Create ray in camera coordinates (normalized)
                    ray_cam = np.array([
                        (gaze_undistorted[0] - camera_matrix[0, 2]) / camera_matrix[0, 0],
                        (gaze_undistorted[1] - camera_matrix[1, 2]) / camera_matrix[1, 1],
                        1.0
                    ])
                    
                    # Transform ray to surface coordinate system
                    # Surface normal is [0, 0, 1] (pointing up)
                    # Plane equation: Z = 0
                    # Ray: P = tvec + t * R^T * ray_cam
                    # Find t where Z = 0
                    
                    ray_surface = R.T @ ray_cam
                    cam_pos_surface = -R.T @ tvec.flatten()
                    
                    # Solve: cam_pos_surface[2] + t * ray_surface[2] = 0
                    if abs(ray_surface[2]) > 0.001:  # Check ray isn't parallel to surface
                        t = -cam_pos_surface[2] / ray_surface[2]
                        
                        # Calculate intersection point
                        gaze_surface_3d = cam_pos_surface + t * ray_surface
                        gaze_surface_x = gaze_surface_3d[0]
                        gaze_surface_y = gaze_surface_3d[1]
                        
                        # Check if gaze is within surface bounds
                        surface_width = markers_config['surface']['width']
                        surface_height = markers_config['surface']['height']
                        
                        if 0 <= gaze_surface_x <= surface_width and 0 <= gaze_surface_y <= surface_height:
                            # Project surface gaze point back to image for visualization
                            gaze_on_surface_3d = np.array([[gaze_surface_x, gaze_surface_y, 0]], dtype=np.float32)
                            gaze_on_surface_2d, _ = cv2.projectPoints(
                                gaze_on_surface_3d, rvec, tvec, camera_matrix, dist_coeffs
                            )
                            gaze_surface_img = gaze_on_surface_2d[0][0].astype(int)
                            
                            # Draw gaze point on surface with crosshair
                            cv2.drawMarker(bgr_buffer, tuple(gaze_surface_img), (255, 255, 0), 
                                         cv2.MARKER_CROSS, 40, 3)
                            
                            # Display surface coordinates
                            coord_text = f"Surface: ({gaze_surface_x:.1f}, {gaze_surface_y:.1f}) mm"
                            cv2.putText(bgr_buffer, coord_text,
                                       (10, 70),
                                       cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2)
                        else:
                            # Gaze is outside surface
                            coord_text = f"Surface: Outside ({gaze_surface_x:.1f}, {gaze_surface_y:.1f}) mm"
                            cv2.putText(bgr_buffer, coord_text,
                                       (10, 70),
                                       cv2.FONT_HERSHEY_SIMPLEX, 0.8, (128, 128, 128), 2)
        
        # Draw detected markers and check gaze
        if ids is not None:
            cv2.aruco.drawDetectedMarkers(bgr_buffer, corners, ids)
            
            # Check which marker is being looked at
            for i, corner in enumerate(corners):
                marker_id = ids[i][0]
                
                # Check if gaze point is inside this marker
                result = cv2.pointPolygonTest(corner[0], gaze_point, False)
                if result >= 0:  # Point is inside or on the marker
                    looked_at_marker = marker_id
                
                # Calculate center of marker
                center = corner[0].mean(axis=0).astype(int)
                
                # Draw center point
                color = (255, 0, 255) if looked_at_marker == marker_id else (0, 255, 0)
                cv2.circle(bgr_buffer, tuple(center), 5, color, -1)
                
                # Add ID label
                cv2.putText(bgr_buffer, f"ID:{marker_id}", 
                           (center[0] + 10, center[1] - 10),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
                
                # Highlight looked-at marker with thicker border
                if looked_at_marker == marker_id:
                    cv2.polylines(bgr_buffer, [corner.astype(int)], True, (255, 0, 255), 3)

        # Draw gaze point
        cv2.circle(
            bgr_buffer,
            gaze_point,
            radius=80,
            color=(0, 0, 255),
            thickness=15,
        )
        
        # Display which marker is being looked at
        status_text = f"Looking at: Marker {looked_at_marker}" if looked_at_marker is not None else "Looking at: None"
        if surface_detected:
            status_text += " | Surface: Detected"
        else:
            status_text += " | Surface: Not detected"
        
        cv2.putText(bgr_buffer, status_text, 
                   (10, 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
        cv2.putText(bgr_buffer, status_text, 
                   (10, 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 1)

        # Write frame to video file if recording
        if video_writer is not None:
            video_writer.write(bgr_buffer)
        
        cv2.imshow("Scene camera with gaze overlay", bgr_buffer)
        if cv2.waitKey(1) & 0xFF == 27:
            break
    
    # Release video writer when done
    if video_writer is not None:
        video_writer.release()
        print(f"Video saved to {record_video}")

async def get_most_recent_item(queue):

    item = await queue.get()

    while True:
        try:
            next_item = queue.get_nowait()
        except asyncio.QueueEmpty:
            return item
        else:
            item = next_item

async def get_closest_item(queue, timestamp):

    item_ts, item = await queue.get()

    # assumes monotonically increasing timestamps

    if item_ts > timestamp:
        return item_ts, item
    
    while True:
        try:
            next_item_ts, next_item = queue.get_nowait()

        except asyncio.QueueEmpty:
            return item_ts, item

        else:
            if next_item_ts > timestamp:
                return next_item_ts, next_item
            item_ts, item = next_item_ts, next_item

def main():
    parser = argparse.ArgumentParser(
                    prog='Pupil Labs camera',
                    description='Display Pupil Labs invisible video feed with eye-gaze',
                    epilog='See README.md for usage.')
    parser.add_argument('-r', '--record-video', type=str, help='record displayed video to file (e.g., myrecording.mp4)')

    args = parser.parse_args()
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(runcam(record_video=args.record_video))

if __name__ == "__main__":
    main()