import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from impact_showcase import DROPS, dense_spawns, drop_mass, runner_group


class ImpactShowcaseTest(unittest.TestCase):
    def test_dense_group_and_collision_control_share_the_same_spawns(self):
        spawns = dense_spawns()
        self.assertEqual(len(spawns), 16)
        self.assertEqual(len(set(spawns)), 16)
        self.assertTrue(.75 <= min(math.dist(spawns[0], p) for p in spawns[1:]) <= 1.0)
        self.assertEqual({runner_group(i, "shared") for i in range(16)}, {0})
        self.assertEqual({runner_group(i, "isolated") for i in range(16)}, set(range(16)))

    def test_sizes_have_one_density_and_mass_scales_with_volume(self):
        self.assertEqual([DROPS[name][0] * 2 for name in ("palm", "medium", "large")], [.12, .45, 1.])
        self.assertEqual(len({density for _,density in DROPS.values()}), 1)
        self.assertAlmostEqual(drop_mass("large")/drop_mass("palm"), (1/.12)**3)
        self.assertEqual(len(set(dense_spawns(100))), 100)


if __name__ == "__main__":
    unittest.main()
