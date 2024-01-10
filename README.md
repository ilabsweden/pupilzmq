# PupilZMQ - A ZeroMq (ZMQ) publisher for the Pupil Labs streaming API

Pupil Labs provide client libraries for theirs streaming API in Python, but if you want to access eye-tracking data in another language you'd need to implement your own client. PupilZMQ provides an alternative by exposing parts of the PupilLabs streaming API as a ZeroMQ (ZMQ) pub-sub pattern, aloing ZMQ clients weitten in a multitude of different languages to access real time eye-tracking data through a simple subscription to a standard ZMQ publisher. 

