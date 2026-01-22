# PupilZMQ - A ZeroMq (ZMQ) publisher for the Pupil Labs streaming API

Pupil Labs provide [client libraries](https://docs.pupil-labs.com/invisible/real-time-api/tutorials/) for their [streaming API](https://pupil-labs-realtime-api.readthedocs.io/en/stable/guides/under-the-hood.html) in Python, but if you want to access eye-tracking data in another language you'd need to implement your own client. PupilZMQ provides an alternative by exposing parts of the PupilLabs streaming API as a [ZeroMQ (ZMQ)](https://zeromq.org/) [pub-sub pattern](https://zguide.zeromq.org/docs/chapter1/), aloing ZMQ clients weitten in a multitude of different languages to access real time eye-tracking data through a simple subscription to a standard ZMQ publisher. 

## Installation

    pip install -r requirements.txt

## Camera display 

The `pupilcam.py` script displays the live video feed from Pupil Labs Invisible glasses with real-time gaze overlay.

### Usage

```bash
python pupilcam.py
```

**Options:**
- `-r, --record-video <filename>`: Record the displayed video with gaze overlay to an MP4 file

**Examples:**
```bash
# Basic display
python pupilcam.py

# Record video
python pupilcam.py -r recording.mp4
```

**Controls:**
- Press `ESC` to exit
- Click window close button (X) to exit

**What it shows:**
- Live scene camera feed from Pupil Labs glasses
- Red circle overlay showing current gaze position

## Tracker

The `pupiltrack.py` script provides advanced tracking capabilities with ArUco marker detection, gaze tracking, and video recording.

### Preparation 

Print ArUco codes from https://chev.me/arucogen/ 

**Recommended settings:**
- Dictionary: **4x4 (100)**
- Marker IDs: 0-19 (for 20 markers)
- Minimum size: 5cm × 5cm (larger is better for distance detection)
- Print on white paper with good contrast

### Usage

```bash
python pupiltrack.py
```

**Options:**
- `-r, --record-video <filename>`: Record the displayed video with all overlays to an MP4 file

**Examples:**
```bash
# Basic tracking
python pupiltrack.py

# Record video to file
python pupiltrack.py -r myrecording.mp4
```

**Controls:**
- Press `ESC` to exit and save recording

**What it shows:**
- Live scene camera feed with gaze overlay (red circle)
- Detected ArUco markers with green borders
- Marker IDs labeled next to each marker
- Currently viewed marker highlighted in magenta
- Status display showing which marker is being looked at

## Publish-subscribe

The publisher-subscriber pattern allows you to stream Pupil Labs data to other applications via ZeroMQ.

### Publisher (`pupilpub.py`)

Streams real-time gaze data from Pupil Labs Invisible glasses over ZeroMQ. Data is published as JSON messages containing gaze coordinates, worn status, and timestamps.

**Usage:**
```bash
python pupilpub.py [address] [-t TOPIC] [--dummy]
```

**Arguments:**
- `address`: Interface and port to bind to (default: `*:5555`)
  - Format: `interface:port`
  - Use `*` to bind to all interfaces
  - Example: `localhost:5555` or `*:5555`
- `-t, --topic`: ZMQ topic name for published messages (default: `pupil/gaze`)
- `--dummy`: Stream dummy data without connecting to glasses (useful for testing)

**Examples:**
```bash
# Publish on default port (5555) on all interfaces
python pupilpub.py

# Publish on specific port
python pupilpub.py *:6000

# Publish with custom topic
python pupilpub.py -t eyetracking/data

# Test with dummy data (square pattern)
python pupilpub.py --dummy
```

**Message format:**
```json
{
  "x": 544.2,
  "y": 320.5,
  "worn": true,
  "timestamp": 1737532800.123456
}
```

### Subscriber (`pupilsub.py`)

Minimal reference implementation showing how to subscribe to gaze data from `pupilpub.py`.

**Usage:**
```bash
python pupilsub.py [address] [-t TOPIC]
```

**Arguments:**
- `address`: Address and port to connect to (default: `localhost:5555`)
  - Format: `hostname:port`
  - Example: `localhost:5555` or `192.168.1.100:5555`
- `-t, --topic`: ZMQ topic to subscribe to (default: `pupil/gaze`)

**Examples:**
```bash
# Subscribe to local publisher
python pupilsub.py

# Subscribe to remote publisher
python pupilsub.py 192.168.1.100:5555

# Subscribe to custom topic
python pupilsub.py -t eyetracking/data
```

**Output:**
```
Received topic pupil/gaze: {'x': 544.2, 'y': 320.5, 'worn': True, 'timestamp': 1737532800.123456}
```

### Using with other languages

Since ZeroMQ has [bindings for many languages](https://zeromq.org/languages/), you can subscribe to the gaze data stream from C#, C++, Java, JavaScript, Unity, and more. See the `UnityAssets/GazeSubscriber.cs` for a C# Unity example.


