"""Expose Pupil Labs invisible eye-gaze data on ZMQ pub socket. 
"""

import asyncio
import zmq, zmq.asyncio
import json
from datetime import datetime
import contextlib
import argparse, os
import random

from pupil_labs.realtime_api import (
    Device,
    Network,
    receive_gaze_data
)

ctx = zmq.asyncio.Context()

async def runpub(address,topic):
    pub = ctx.socket(zmq.PUB)
    pub.bind(address)

    topic = topic.encode('utf8')

    async with Network() as network:
        dev_info = await network.wait_for_new_device(timeout_seconds=5)

    if dev_info is None:
        print("No device could be found! Abort")
        return

    async with Device.from_discovered_device(dev_info) as device:
        print(f"Getting status information from {device}")
        status = await device.get_status()
        sensor_gaze = status.direct_gaze_sensor()
        #sensor_eye = status.direct_eyes_sensor()
        
        if sensor_gaze.connected:
            print(f'Publishing events on {address}, topic: {topic.decode("utf8")}')
        else:
            print(f"Gaze sensor is not connected to {device}")
            return

        restart_on_disconnect = True
        async for gaze in receive_gaze_data(sensor_gaze.url, run_loop=restart_on_disconnect):
            pub.send_multipart([topic, gaze_to_json(gaze)])

async def rundomDummy(address,topic):
    pub = ctx.socket(zmq.PUB)
    pub.bind(address)

    topic = topic.encode('utf8')

    print(f'Publishing dummy events on {address}, topic: {topic.decode("utf8")}')
        
    while True:
        await send_dummy()

async def squareDummy(address,topic):
    sceneCamResolution = (1088,1080)
    pub = ctx.socket(zmq.PUB)
    pub.bind(address)

    topic = topic.encode('utf8')

    print(f'Publishing square dummy events on {address}, topic: {topic.decode("utf8")}')

    while True:
        x = 0
        y = 0
        for x in range(0,sceneCamResolution[0],10):
            await send_dummy(pub,topic,x,y)
        for y in range(0,sceneCamResolution[1],10):
            await send_dummy(pub,topic,x,y)    
        for x in range(sceneCamResolution[0],0,-10):
            await send_dummy(pub,topic,x,y)
        for y in range(sceneCamResolution[1],0,-10):
            await send_dummy(pub,topic,x,y)

async def send_dummy(pub,topic,x,y):
    ts = datetime.now().timestamp()
    pub.send_multipart([topic, gaze_to_json((x,y,True,ts))])
    await asyncio.sleep(0.01)

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
    parser.add_argument('address',help='specifies the interface:port to bind to',default='*:5555',nargs='?')
    parser.add_argument('-t','--topic',help='the zmq topic on which events are published',default='pupil/gaze')
    parser.add_argument('--dummy',action='store_true',help='publisher streams dummy data without connecting to eye tracker')

    args = parser.parse_args()
    with contextlib.suppress(KeyboardInterrupt):
        if args.dummy:
            asyncio.run(squareDummy('tcp://' + args.address,args.topic))
        else:
            asyncio.run(runpub('tcp://' + args.address,args.topic))

if __name__ == "__main__":
    main()