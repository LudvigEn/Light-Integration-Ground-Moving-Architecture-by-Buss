"""Check the shareable archive independently of the repository layout."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

from package_simulator import build_archive
from simulator import DEFAULT_IMAGE


class DistributionTests(unittest.TestCase):
    def test_archive_runs_after_extraction_without_repository_or_local_state(self):
        with tempfile.TemporaryDirectory(prefix='simulator share ') as folder:
            root = Path(folder)
            archive = build_archive(root / 'simulator.zip')
            with zipfile.ZipFile(archive) as bundle:
                for name in bundle.namelist():
                    self.assertFalse(any(part in name.split('/') for part in
                                         ('.state', '.venv', '__pycache__', 'secrets.py')))
                    self.assertFalse(name.endswith(('.img', '.pyc')))
                self.assertEqual(bundle.getinfo('t4s3-simulator/Launch.command').external_attr >> 16 & 0o111,
                                 0o111)
                bundle.extractall(root / 'unpacked')
            simulator = root / 'unpacked' / 't4s3-simulator'
            result = subprocess.run([sys.executable, str(simulator / 'simulator.py'), '--help'],
                                    cwd=root, capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('--wifi-ssid', result.stdout)
            self.assertTrue((simulator / 'fonts' / 'sim_montserrat_16.bin').is_file())
            self.assertTrue((simulator / 'test-data' / 'stop_740032188_formatted.json').is_file())

    @unittest.skipUnless(DEFAULT_IMAGE.is_file(), 'Build the application image first')
    def test_extracted_archive_boots_application_and_loads_sample_departures(self):
        with tempfile.TemporaryDirectory(prefix='simulator standalone ') as folder:
            root = Path(folder)
            with zipfile.ZipFile(build_archive(root / 'simulator.zip')) as bundle:
                bundle.extractall(root / 'unpacked')
            simulator = root / 'unpacked' / 't4s3-simulator'
            script = '''
import sys
import tempfile
from simulator import Simulator
with tempfile.TemporaryDirectory() as state:
    app = Simulator(sys.argv[1], hidden=True, local_data=True, state_dir=state)
    try:
        app.boot()
        assert 'app' in app.scope, app.console.get('1.0', 'end')
        target = app.scope['app']
        app.move(1, 0)
        app.move(1, 0)
        assert len(target.dep_scr.children) > 2, app.console.get('1.0', 'end')
    finally:
        app.close()
'''
            result = subprocess.run([sys.executable, '-c', script, str(DEFAULT_IMAGE)],
                                    cwd=simulator, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
