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

async def runcam(record=None, record_video=None):
    
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
            await match_and_draw(queue_video, queue_gaze, await initFrameFolder(record), record_video)

        finally:
            process_video.cancel()
            process_gaze.cancel()

async def enqueue_sensor_data(sensor: T.AsyncIterator, queue: asyncio.Queue) -> None:

    async for datum in sensor:
        try:
            queue.put_nowait((datum.datetime, datum))

        except asyncio.QueueFull:
            print(f"Queue is full, dropping {datum}")

async def initFrameFolder(record):
    if not record: return

    now = datetime.now()
    dt_string = now.strftime("%Y-%m-%d_%H%M%S")
    await aiofiles.os.makedirs(record, exist_ok=True)
    frameFolder = os.path.join(record,dt_string)
    await aiofiles.os.makedirs(frameFolder)
    return frameFolder

async def saveFrame(frameFolder, frame, index):
    if index % 10 == 0:
        cv2.imwrite(os.path.join(frameFolder,'Frame%d.png'%index),frame)

async def match_and_draw(queue_video, queue_gaze, record=None, record_video=None):
    frameIndex = 0
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

        if record:
            asyncio.create_task(saveFrame(record,bgr_buffer.copy(),frameIndex))

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

        frameIndex+=1
    
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
    parser.add_argument('--record', nargs='?', help='enables recording frames to specified output folder')
    parser.add_argument('-r', '--record-video', type=str, help='record displayed video to file (e.g., myrecording.mp4)')

    args = parser.parse_args()
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(runcam(args.record, args.record_video))

if __name__ == "__main__":
    main()