# PupilZMQ - A ZeroMq (ZMQ) publisher for the Pupil Labs streaming API

Pupil Labs provide [client libraries](https://docs.pupil-labs.com/invisible/real-time-api/tutorials/) for their [streaming API](https://pupil-labs-realtime-api.readthedocs.io/en/stable/guides/under-the-hood.html) in Python, but if you want to access eye-tracking data in another language you'd need to implement your own client. PupilZMQ provides an alternative by exposing parts of the PupilLabs streaming API as a [ZeroMQ (ZMQ)](https://zeromq.org/) [pub-sub pattern](https://zguide.zeromq.org/docs/chapter1/), aloing ZMQ clients weitten in a multitude of different languages to access real time eye-tracking data through a simple subscription to a standard ZMQ publisher. 

