"""Minimal reference implementation of a subscriber to eye-gaze data from pupilpub. 
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
            print('Received topic {}:'.format(t.decode('utf8')),json.loads(msg))

    except KeyboardInterrupt:
        pass

def main():
    parser = argparse.ArgumentParser(
                    prog='Pupil Labs ZMQ publisher',
                    description='Expose Pupil Labs invisible eye-gaze data on ZMQ pub socket',
                    epilog='See README.md for usage.')
    parser.add_argument('address',help='specifies the address:port to connect to',default='localhost:5555',nargs='?')
    parser.add_argument('-t','--topic',help='the zmq topic on which events are published',default='pupil/gaze')

    args = parser.parse_args()
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(runsub('tcp://' + args,args.topic))

if __name__ == "__main__":
    main()