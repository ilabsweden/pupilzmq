"""Expose Pupil Labs invisible eye-gaze data on ZMQ pub socket. 

Modified from the async demo from Pupil Labs documentation, https://pupil-labs-realtime-api.readthedocs.io/en/stable/examples/async.html 
"""

import asyncio
import zmq, zmq.asyncio
import json

import contextlib
import typing as T
import cv2
import argparse, os
from datetime import datetime

from pupil_labs.realtime_api import (
    Device,
    Network,
    receive_gaze_data
)

ctx = zmq.asyncio.Context()

async def runpub(address):
    pub = ctx.socket(zmq.PUB)
    pub.bind(address)

    topic = b'pupil/gaze'

    async with Network() as network:
        dev_info = await network.wait_for_new_device(timeout_seconds=5)

    if dev_info is None:
        print("No device could be found! Abort")
        return

    async with Device.from_discovered_device(dev_info) as device:
        print(f"Getting status information from {device}")
        status = await device.get_status()
        sensor_gaze = status.direct_gaze_sensor()
        sensor_eye = status.direct_eyes_sensor()
        
        if not sensor_gaze.connected:
            print(f"Gaze sensor is not connected to {device}")
            return

        restart_on_disconnect = True
        async for gaze in receive_gaze_data(sensor_gaze.url, run_loop=restart_on_disconnect):
            #print(gaze_to_json(gaze,True))
            pub.send_multipart([topic, gaze_to_json(gaze)])

async def runsub(address):
    sub = ctx.socket(zmq.SUB)
    sub.connect(address)

    topic = b''
    sub.setsockopt(zmq.SUBSCRIBE, topic)

    try:
        while True:
            t, msg = await sub.recv_multipart()
            print('Received topic {}:'.format(t.decode('utf8')),json.loads(msg))

    except KeyboardInterrupt:
        pass

def gaze_to_json(gaze,encode='utf8'):
    g = {'x':gaze[0],'y':gaze[1],'worn':gaze[2],'timestamp':gaze[3]}
    if encode:
        g = json.dumps(g)
        if isinstance(encode,str):
            g = g.encode(encode)
    return g

def main():
    parser = argparse.ArgumentParser(
                    prog='Pupil Labs ZMQ publisher',
                    description='Expose Pupil Labs invisible eye-gaze data on ZMQ pub socket',
                    epilog='See README.md for usage.')
    parser.add_argument('address',help='specifies the interface:port onto which to bind',default='*:5555',nargs='?')
    parser.add_argument('-s','--sub',action='store_true',help='executes a minimal reference subscriber that listens to published events from specified address')

    args = parser.parse_args()
    with contextlib.suppress(KeyboardInterrupt):
        if args.sub:
            asyncio.run(runsub('tcp://' + args.address.replace('*','localhost')))
        else:
            asyncio.run(runpub('tcp://' + args.address))

if __name__ == "__main__":
    main()