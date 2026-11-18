"""Known synthetic matrix: validate units, axis order, bias, and bounds.
This is NOT a calibration for the connected sensor.
"""

from pathlib import Path
import tempfile
import unittest
from ati_daq_ft.core import Calibration


class ConversionTest(unittest.TestCase):
    def test_identity_and_tare(self):
        axes = "".join(
            f'<Axis Name="{name}" values="'
            + " ".join("1" if i == j else "0" for j in range(6))
            + '"/>'
            for i, name in enumerate(["Fx", "Fy", "Fz", "Tx", "Ty", "Tz"])
        )
        xml = (
            '<FTSensor Serial="SYNTHETIC_TEST_ONLY" BodyStyle="Gamma" NumGages="6" Family="DAQ"><Calibration PartNumber="TEST" CalDate="TEST" ForceUnits="N" TorqueUnits="N-mm" DistUnits="mm"><BasicTransform/>'
            + axes
            + "</Calibration></FTSensor>"
        )
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "synthetic.cal"
            p.write_text(xml)
            c = Calibration(p)
            try:
                values = [1, 2, 3, 4, 5, 6, 0.5]
                self.assertEqual(c.serial, "SYNTHETIC_TEST_ONLY")
                for x, y in zip(c.convert(values), [1, 2, 3, 0.004, 0.005, 0.006]):
                    self.assertAlmostEqual(x, y, places=6)
                c.bias(values)
                for x in c.convert(values):
                    self.assertAlmostEqual(x, 0, places=6)
                for x, y in zip(
                    c.convert([2, 3, 4, 5, 6, 7, 0.5]), [1, 1, 1, 0.001, 0.001, 0.001]
                ):
                    self.assertAlmostEqual(x, y, places=6)
                c.clear_bias()
                for x, y in zip(c.convert(values), [1, 2, 3, 0.004, 0.005, 0.006]):
                    self.assertAlmostEqual(x, y, places=6)
            finally:
                c.close()

    def test_invalid_dimensions_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "invalid.cal"
            p.write_text('<FTSensor NumGages="100"/>')
            with self.assertRaises(ValueError):
                Calibration(p)


if __name__ == "__main__":
    unittest.main()
