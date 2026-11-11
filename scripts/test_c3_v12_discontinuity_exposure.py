import unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from c3_v12_discontinuity_exposure import flagged
class ExposureTests(unittest.TestCase):
 def test_exact_upward_half(self):self.assertTrue(flagged(100,150))
 def test_exact_downward_third(self):self.assertTrue(flagged(300,200))
 def test_no_intermediate_fake_critical_moves(self):
    self.assertFalse(flagged(100,120))
    self.assertFalse(flagged(100,75))
 def test_no_zero_bars_are_trusted_by_downstream(self):
    # Source bar validator rejects zero; audit is a threshold classifier only.
    self.assertTrue(flagged(100,0))
if __name__=="__main__":unittest.main()
