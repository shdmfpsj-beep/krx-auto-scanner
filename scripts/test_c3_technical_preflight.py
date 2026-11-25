"""Run the production post-render preflight, including its real geometry imports."""
import ast
import unittest
import textwrap
from test_c3_top5_pipeline import embedded


class TechnicalPreflightTests(unittest.TestCase):
    def run_preflight(self, **changes):
        body=embedded('Collect KRX sessions and render one classic image per stock')
        imports=[n for n in ast.walk(ast.parse(body)) if isinstance(n,ast.ImportFrom) and n.module=='c3_entry_geometry']
        self.assertTrue(imports)
        namespace={}
        for node in imports:
            exec(compile(ast.Module(body=[node],type_ignores=[]),'production geometry imports','exec'),namespace)
        row=dict(code='111111',entry_watch_low=9900,entry_watch_high=10000,
                 structural_stop_ref=9700,r1_ref=10300,r2_ref=None,
                 chart_bars=[dict(date='20261124') for _ in range(60)])
        row.update(changes)
        namespace.update(selected=[row],days=['20261124'])
        lines=body.splitlines()
        start=next(i for i,line in enumerate(lines) if line.lstrip().startswith("def tick_ok("))
        end=next(i for i,line in enumerate(lines) if "receipt['price_integrity']" in line)
        block=textwrap.dedent("\n".join(lines[start:end]))
        exec(compile(block,'production post-render preflight','exec'),namespace)
        return namespace

    def test_real_imports_support_nonempty_executable_price_preflight(self):
        self.assertTrue(self.run_preflight()['tick_ok'](10000))
    def test_real_preflight_still_rejects_risk_above_five_percent(self):
        with self.assertRaisesRegex(ValueError,'POST_ROUNDING_RISK_INVALID'):
            self.run_preflight(structural_stop_ref=9400)
    def test_real_preflight_still_rejects_invalid_ticks_and_bar_dates(self):
        with self.assertRaisesRegex(ValueError,'NON_EXECUTABLE_PRICE'):
            self.run_preflight(entry_watch_high=10003)
        with self.assertRaisesRegex(ValueError,'CHART_SOURCE_MISMATCH'):
            self.run_preflight(chart_bars=[dict(date='20261123') for _ in range(60)])


if __name__=='__main__':unittest.main()
