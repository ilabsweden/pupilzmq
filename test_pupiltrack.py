import importlib.util
import sys
import types
import unittest

import numpy as np

pupil_labs_module = types.ModuleType('pupil_labs')
realtime_api_module = types.ModuleType('pupil_labs.realtime_api')
realtime_api_module.Device = object
realtime_api_module.Network = object
realtime_api_module.receive_gaze_data = lambda *args, **kwargs: None
realtime_api_module.receive_video_frames = lambda *args, **kwargs: None

sys.modules['pupil_labs'] = pupil_labs_module
sys.modules['pupil_labs.realtime_api'] = realtime_api_module

spec = importlib.util.spec_from_file_location(
    'pupiltrack_mod',
    '/Users/sander/Documents/Source/pupilzmq/pupiltrack.py',
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class MarkerIdNormalizationTests(unittest.TestCase):
    def test_single_marker_1d_array(self):
        ids = np.array([7], dtype=np.int32)
        self.assertEqual(module.normalize_marker_ids(ids), [7])

    def test_single_marker_2d_array(self):
        ids = np.array([[7]], dtype=np.int32)
        self.assertEqual(module.normalize_marker_ids(ids), [7])


if __name__ == '__main__':
    unittest.main()
