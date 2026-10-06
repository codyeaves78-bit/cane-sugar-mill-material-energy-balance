import unittest
from types import SimpleNamespace

from Condenser import Condenser
from CoolingTowerSystem import CoolingTowerSystem


class DownlegTests(unittest.TestCase):
    def condenser(self, drop=5, temperature=130):
        vapor = SimpleNamespace(sat_temp_deg_F=temperature,
                                flow_lb_per_hr=50000, h_fg=1020)
        return Condenser(vapor, 85, drop)

    def test_global_drop_and_balances(self):
        a, b = self.condenser(), self.condenser(7, 140)
        system = CoolingTowerSystem([('Pan', a), b], 85,
                                   water_outlet_temp_drop_F=10)
        for c in (a, b):
            self.assertEqual(c.water_out_temp_drop_F, 10)
            self.assertEqual(c.water_outlet_temp_F, c.vapor_sat_temp_F - 10)
            expected = 50000 * (1020 + 10) / (c.vapor_sat_temp_F - 10 - 85)
            self.assertAlmostEqual(c.injection_water_flow_lb_hr, expected)
            self.assertAlmostEqual(c.heat_load_btu_hr,
                                   c.injection_water_flow_lb_hr *
                                   (c.water_outlet_temp_F - c.water_inlet_temp_F))
        self.assertAlmostEqual(system.balance_check['diff_lb_hr'], 0, places=6)

    def test_omitted_drop_preserves_individual_settings(self):
        a, b = self.condenser(3), self.condenser(7)
        CoolingTowerSystem([a, b], 85)
        self.assertEqual((a.water_out_temp_drop_F, b.water_out_temp_drop_F), (3, 7))

    def test_zero_drop_and_increasing_water_demand(self):
        flows = []
        for drop in (0, 5, 10):
            system = CoolingTowerSystem([self.condenser()], 85,
                                       water_outlet_temp_drop_F=drop)
            flows.append(system.total_injection_water_lb_hr)
        self.assertLess(flows[0], flows[1])
        self.assertLess(flows[1], flows[2])

    def test_makeup_blend(self):
        system = CoolingTowerSystem([self.condenser()], 85, 10, 70, 30,
                                   water_outlet_temp_drop_F=10)
        self.assertGreater(system.makeup_lb_hr, 0)
        self.assertAlmostEqual(system.condensers[0][1].water_inlet_temp_F,
                               system.delivered_water_temp_F, places=6)
        self.assertAlmostEqual(system.balance_check['diff_lb_hr'], 0, places=6)

    def test_invalid_drop(self):
        for drop in (-1, float('nan'), float('inf')):
            with self.subTest(drop=drop), self.assertRaises(ValueError):
                CoolingTowerSystem([self.condenser()], water_outlet_temp_drop_F=drop)

    def test_downleg_must_exceed_injection_temperature(self):
        for drop in (45, 46):
            with self.subTest(drop=drop), self.assertRaisesRegex(ValueError, 'downleg outlet'):
                CoolingTowerSystem([self.condenser()], 85,
                                   water_outlet_temp_drop_F=drop)


if __name__ == '__main__':
    unittest.main()
