"""Offline-only regression for the upstream renderer constructor contract."""
import os,pathlib,sys,unittest
from unittest.mock import patch
os.environ['LITELLM_LOCAL_MODEL_COST_MAP']='True'
sys.path.insert(0,str(pathlib.Path(os.getenv('DSA_FIXED_SOURCE',str(pathlib.Path(__file__).resolve().parents[2]))).resolve()))
from nvda_frozen_once import render_native_report

class NativeRenderTests(unittest.TestCase):
    def test_upstream_constructor_accepts_no_config_argument(self):
        from src.notification import NotificationService
        import inspect
        self.assertNotIn('config',inspect.signature(NotificationService).parameters)

    def test_controller_uses_no_argument_constructor_and_local_renderer(self):
        parsed=object()
        with patch('src.notification.NotificationService',autospec=True) as cls:
            cls.return_value.generate_single_stock_report.return_value='offline report'
            self.assertEqual(render_native_report(parsed),'offline report')
            cls.assert_called_once_with()
            cls.return_value.generate_single_stock_report.assert_called_once_with(parsed)

if __name__=='__main__':unittest.main()
