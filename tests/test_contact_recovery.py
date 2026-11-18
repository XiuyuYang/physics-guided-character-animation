import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from contact_recovery import recovery_start, transition_path, transition_weight


class RecoveryTest(unittest.TestCase):
    def test_waits_until_upright_and_supported_after_a_fall(self):
        heights = np.array([.9]*10 + [.2]*10 + [.8]*30)
        feet = np.zeros((50,2))
        feet[25:,0] = 120
        self.assertEqual(recovery_start(heights, feet), 27)
        self.assertIsNone(recovery_start(heights, np.zeros_like(feet)))

    def test_keeps_impact_and_entry_in_place_then_joins_run_at_matching_speed(self):
        raw = np.array([[i*3., -i*.5] for i in range(50)])
        out = transition_path(raw, 10, 40, 11.)
        np.testing.assert_array_equal(out[:11], raw[:11])
        np.testing.assert_allclose(out[-1]-out[-2],[11.,0.])
        self.assertGreater(out[40,0]-out[39,0],10.9)
        self.assertEqual(transition_weight(0),0.)
        self.assertEqual(transition_weight(1),1.)
