"""Minimal reference implementation of a subscriber to eye-gaze data from pupiltrack.
"""

import asyncio
import zmq, zmq.asyncio
import json

import contextlib
import argparse, os

ctx = zmq.asyncio.Context()

async def runsub(address,topic):
    sub = ctx.socket(zmq.SUB)
    sub.connect(address)

    topic = topic.encode('utf8')
    sub.setsockopt(zmq.SUBSCRIBE, topic)

    try:
        while True:
            t, msg = await sub.recv_multipart()
            gaze = json.loads(msg)
            coords = ', '.join(f"{name}=({point['x']:.1f}, {point['y']:.1f})" for name, point in gaze.items())
            print(f"[{t.decode('utf8')}] {coords}")

    except KeyboardInterrupt:
        pass

def main():
    parser = argparse.ArgumentParser(
                    prog='Pupil Labs ZMQ subscriber',
                    description='Receive camera- and surface-centered eye-gaze coordinates published by pupiltrack',
                    epilog='See README.md for usage.')
    parser.add_argument('address',help='specifies the address:port to connect to',default='localhost:5556',nargs='?')
    parser.add_argument('-t','--topic',help='the zmq topic on which events are published',default='pupil/gaze')

    args = parser.parse_args()
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(runsub('tcp://' + args.address,args.topic))

if __name__ == "__main__":
    main()