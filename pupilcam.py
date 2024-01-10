"""Display Pupil Labs invisible video feed with eye-gaze

Based on the async demo from Pupil Labs documentation, https://pupil-labs-realtime-api.readthedocs.io/en/stable/examples/async.html 
"""

import asyncio
import contextlib
import typing as T
import cv2
import argparse, os
from datetime import datetime

from pupil_labs.realtime_api import (
    Device,
    Network,
    receive_gaze_data,
    receive_video_frames,
)

async def runcam(record=None):
    
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
            await match_and_draw(queue_video, queue_gaze, await initFrameFolder(record))

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

async def match_and_draw(queue_video, queue_gaze,record=None):
    frameIndex = 0

    while True:
        video_datetime, video_frame = await get_most_recent_item(queue_video)
        _, gaze_datum = await get_closest_item(queue_gaze, video_datetime)
        bgr_buffer = video_frame.to_ndarray(format="bgr24")

        if record:
            asyncio.create_task(saveFrame(record,bgr_buffer.copy(),frameIndex))

        cv2.circle(
            bgr_buffer,
            (int(gaze_datum.x), int(gaze_datum.y)),
            radius=80,
            color=(0, 0, 255),
            thickness=15,
        )

        cv2.imshow("Scene camera with gaze overlay", bgr_buffer)
        if cv2.waitKey(1) & 0xFF == 27:
            break

        frameIndex+=1

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
    parser.add_argument('--record', nargs='?', help='enables recording to specified output folder')

    args = parser.parse_args()
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(runcam(args.record))

if __name__ == "__main__":
    main()