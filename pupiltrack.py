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
import zmq
import zmq.asyncio

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


def normalize_marker_ids(ids):
    """Return marker IDs as a flat 1D list for OpenCV 4.x variations."""
    if ids is None:
        return []

    ids_array = np.asarray(ids)
    if ids_array.size == 0:
        return []

    return ids_array.reshape(-1).astype(int).tolist()


# cv::Point coordinates are a 32-bit C++ int; an ill-conditioned solvePnP pose
# (e.g. a single marker seen at a grazing angle) can project points far
# outside the image, even to NaN/inf. Clamp well within the int32 range so
# such points still draw (harmlessly off-screen) instead of making OpenCV
# 5's stricter bindings raise a Bad argument error.
_MAX_POINT_COORD = 1_000_000


def to_opencv_point(point):
    """Convert a point-like array to a plain (x, y) tuple for OpenCV.

    OpenCV 5 is stricter about shape validation, and point arrays can arrive as
    (x, y), (1, 2), (2, 1), or nested lists. Flattening and coercing to int
    keeps all callers compatible.
    """
    coords = np.asarray(point, dtype=np.float64).reshape(-1)
    if coords.size < 2:
        raise ValueError(f"Expected at least two coordinates, got {point!r}")

    coords = np.clip(np.nan_to_num(coords), -_MAX_POINT_COORD, _MAX_POINT_COORD)
    return (int(coords[0]), int(coords[1]))


def project_to_int_points(points):
    """Cast projected points to int, clamping non-finite or out-of-range values.

    See to_opencv_point for why: an unstable solvePnP pose can make
    projectPoints return NaN/inf, or finite values too large for cv::Point's
    32-bit range.
    """
    clamped = np.clip(np.nan_to_num(points), -_MAX_POINT_COORD, _MAX_POINT_COORD)
    return clamped.astype(int)


def load_markers_config(config_file='markers_a0.json'):
    """Load one or more named surface configurations from a JSON file.

    Each top-level key is a surface name; its value defines the surface's
    size and the ArUco markers placed on it, e.g.:
        {"A0": {"width": 1189, "height": 841, "markers": [...]}}
    """
    with open(config_file, 'r') as f:
        config = json.load(f)

    surfaces = {}
    for surface_name, surface in config.items():
        width_mm = surface['width']
        height_mm = surface['height']

        # Build 3D object points for each marker in the surface coordinate system
        # Origin is top-left corner of surface, Y axis points down, X axis points right
        marker_ids = []
        marker_obj_points = []
        for marker in surface['markers']:
            marker_id = marker['id']
            size_mm = marker['size']
            pos_x = marker['position']['x']
            pos_y = marker['position']['y']

            # Define the 4 corners of the marker in 3D (Z=0, planar surface)
            # Marker is centered at position
            half_size = size_mm / 2.0
            marker_ids.append(marker_id)
            marker_obj_points.append(np.array([
                [pos_x - half_size, pos_y - half_size, 0],  # Top-left
                [pos_x + half_size, pos_y - half_size, 0],  # Top-right
                [pos_x + half_size, pos_y + half_size, 0],  # Bottom-right
                [pos_x - half_size, pos_y + half_size, 0]   # Bottom-left
            ], dtype=np.float32))

        # ArUco board: lets us estimate the surface pose from whichever subset
        # of its markers is currently visible, using OpenCV's own (and
        # better-tested) marker-to-point matching instead of hand-rolled
        # correspondence bookkeeping.
        board = cv2.aruco.Board(marker_obj_points, aruco_dict, np.array(marker_ids, dtype=np.int32))

        # Define surface corners for drawing borders
        surface_corners_3d = np.array([
            [0, 0, 0],
            [width_mm, 0, 0],
            [width_mm, height_mm, 0],
            [0, height_mm, 0]
        ], dtype=np.float32)

        surfaces[surface_name] = {
            'width': width_mm,
            'height': height_mm,
            'board': board,
            'surface_corners_3d': surface_corners_3d,
        }

    return surfaces

# Load surface configurations at startup
surfaces_config = load_markers_config()

async def runcam(record_video=None, pub_address='tcp://*:5556', topic='pupil/gaze'):
    zmq_ctx = zmq.asyncio.Context()
    pub = zmq_ctx.socket(zmq.PUB)
    pub.bind(pub_address)
    topic = topic.encode('utf8')
    print(f"Publishing gaze coordinates on {pub_address}, topic: {topic.decode('utf8')}")

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
            await match_and_draw(queue_video, queue_gaze, record_video, pub, topic)

        finally:
            process_video.cancel()
            process_gaze.cancel()
            pub.close()

async def enqueue_sensor_data(sensor: T.AsyncIterator, queue: asyncio.Queue) -> None:

    async for datum in sensor:
        try:
            queue.put_nowait((datum.datetime, datum))

        except asyncio.QueueFull:
            print(f"Queue is full, dropping {datum}")

async def match_and_draw(queue_video, queue_gaze, record_video=None, pub=None, topic=b'pupil/gaze'):
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
        
        # Estimate the pose of each configured surface if markers are detected
        detected_surfaces = []
        surface_status_lines = []
        surface_coords = {}
        if ids is not None:
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

            for surface_name, surface in surfaces_config.items():
                # Match this surface's board against whichever markers are
                # visible this frame (any subset, in any order)
                obj_points, img_points = surface['board'].matchImagePoints(corners, ids)

                # Need at least one marker to estimate pose
                if obj_points is None or len(obj_points) == 0:
                    continue

                # Solve PnP to get rotation and translation vectors
                success, rvec, tvec = cv2.solvePnP(obj_points, img_points, camera_matrix, dist_coeffs)

                if not success:
                    continue

                detected_surfaces.append(surface_name)

                # Project surface corners to image
                surface_corners_2d, _ = cv2.projectPoints(
                    surface['surface_corners_3d'], rvec, tvec, camera_matrix, dist_coeffs
                )
                surface_corners_2d = project_to_int_points(surface_corners_2d.reshape(-1, 2))

                # Draw surface border
                cv2.polylines(bgr_buffer, [surface_corners_2d], True, (0, 255, 255), 3)

                # Add corner labels
                corner_labels = ['TL', 'TR', 'BR', 'BL']
                for corner, label in zip(surface_corners_2d, corner_labels):
                    cv2.circle(bgr_buffer, to_opencv_point(corner), 8, (0, 255, 255), -1)
                    cv2.putText(bgr_buffer, f"{surface_name} {label}", to_opencv_point(corner + np.array([10, -10])),
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
                if abs(ray_surface[2]) <= 0.001:  # Ray is parallel to surface
                    continue

                t = -cam_pos_surface[2] / ray_surface[2]

                # Calculate intersection point
                gaze_surface_3d = cam_pos_surface + t * ray_surface
                gaze_surface_x = gaze_surface_3d[0]
                gaze_surface_y = gaze_surface_3d[1]
                surface_coords[surface_name] = (gaze_surface_x, gaze_surface_y)

                # Check if gaze is within surface bounds
                surface_width = surface['width']
                surface_height = surface['height']

                if 0 <= gaze_surface_x <= surface_width and 0 <= gaze_surface_y <= surface_height:
                    # Project surface gaze point back to image for visualization
                    gaze_on_surface_3d = np.array([[gaze_surface_x, gaze_surface_y, 0]], dtype=np.float32)
                    gaze_on_surface_2d, _ = cv2.projectPoints(
                        gaze_on_surface_3d, rvec, tvec, camera_matrix, dist_coeffs
                    )
                    gaze_surface_img = project_to_int_points(gaze_on_surface_2d[0][0])

                    # Draw gaze point on surface with crosshair
                    cv2.drawMarker(bgr_buffer, to_opencv_point(gaze_surface_img), (255, 255, 0),
                                 cv2.MARKER_CROSS, 40, 3)

                    # Display surface coordinates
                    coord_text = f"{surface_name}: ({gaze_surface_x:.1f}, {gaze_surface_y:.1f}) mm"
                    surface_status_lines.append((coord_text, (255, 255, 0)))
                else:
                    # Gaze is outside surface
                    coord_text = f"{surface_name}: Outside ({gaze_surface_x:.1f}, {gaze_surface_y:.1f}) mm"
                    surface_status_lines.append((coord_text, (128, 128, 128)))

        # Display surface coordinates, one line per detected surface
        for i, (coord_text, color) in enumerate(surface_status_lines):
            cv2.putText(bgr_buffer, coord_text,
                       (10, 70 + i * 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)

        # Publish camera- and surface-centered gaze coordinates
        if pub is not None:
            gaze_message = {"camera": {"x": float(gaze_point[0]), "y": float(gaze_point[1])}}
            for surface_name in surfaces_config:
                x, y = surface_coords.get(surface_name, (0.0, 0.0))
                gaze_message[surface_name] = {"x": float(x), "y": float(y)}
            await pub.send_multipart([topic, json.dumps(gaze_message).encode('utf8')])

        # Draw detected markers and check gaze
        if ids is not None:
            marker_ids = normalize_marker_ids(ids)
            cv2.aruco.drawDetectedMarkers(bgr_buffer, corners, ids)

            # Check which marker is being looked at
            for i, corner in enumerate(corners):
                marker_id = marker_ids[i]

                # Check if gaze point is inside this marker
                result = cv2.pointPolygonTest(corner[0], gaze_point, False)
                if result >= 0:  # Point is inside or on the marker
                    looked_at_marker = marker_id

                # Calculate center of marker
                center = corner[0].mean(axis=0).astype(np.float64)

                # Draw center point
                color = (255, 0, 255) if looked_at_marker == marker_id else (0, 255, 0)
                cv2.circle(bgr_buffer, to_opencv_point(center), 5, color, -1)

                # Add ID label
                cv2.putText(bgr_buffer, f"ID:{marker_id}",
                           (to_opencv_point(center)[0] + 10, to_opencv_point(center)[1] - 10),
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
        if detected_surfaces:
            status_text += f" | Surfaces: {', '.join(detected_surfaces)}"
        else:
            status_text += " | Surfaces: None detected"
        
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
    parser.add_argument('-a', '--pub-address', type=str, default='tcp://*:5556', help='ZMQ address to bind the gaze coordinate pub socket to')
    parser.add_argument('-t', '--topic', type=str, default='pupil/gaze', help='ZMQ topic on which gaze coordinates are published')

    args = parser.parse_args()
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(runcam(record_video=args.record_video, pub_address=args.pub_address, topic=args.topic))

if __name__ == "__main__":
    main()