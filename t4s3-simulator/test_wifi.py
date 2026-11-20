"""Exercise the real application's network fallback without hardware or delays."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from simulator import Network


class WifiListTests(unittest.TestCase):
    def setUp(self):
        source = Path(__file__).resolve().parents[1] / 'project' / 'main.py'
        tree = ast.parse(source.read_text(encoding='utf-8'))
        application = next(node for node in tree.body
                           if isinstance(node, ast.ClassDef) and node.name == 'Application')
        self.clock = 0
        self.network = Network(True, available_ssids=['Second'])
        self.log = Mock()
        self.namespace = {
            'network': self.network, 'log': self.log,
            'WIFI_LIST': [('Missing', 'first-password'), ('Second', 'second-password')],
            'WIFI_SSID': 'Second', 'WIFI_PASSWORD': 'legacy-password',
            'time': SimpleNamespace(ticks_ms=lambda: self.clock,
                                    ticks_diff=lambda a, b: a - b,
                                    sleep_ms=self.sleep),
        }
        exec(compile(ast.Module(body=[application], type_ignores=[]), str(source), 'exec'), self.namespace)
        self.connect = self.namespace['Application'].connect_wifi

    def sleep(self, ms):
        self.clock += ms

    def test_missing_first_network_falls_back_without_waiting(self):
        station = self.network.station
        with patch.object(station, 'connect', wraps=station.connect) as attempts:
            self.assertEqual(self.connect(), 'Second')
        self.assertEqual(attempts.call_args_list,
                         [unittest.mock.call('Missing', 'first-password'),
                          unittest.mock.call('Second', 'second-password')])
        self.assertEqual(self.clock, 0)
        self.assertTrue(station.isconnected())
        self.assertNotIn('password', str(self.log.call_args_list))

    def test_first_available_network_wins(self):
        self.network.available_ssids = {'Missing', 'Second'}
        with patch.object(self.network.station, 'connect', wraps=self.network.station.connect) as attempts:
            self.assertEqual(self.connect(), 'Missing')
        attempts.assert_called_once_with('Missing', 'first-password')

    def test_connecting_network_times_out_then_tries_next(self):
        station = self.network.station
        original_connect = station.connect

        def connect(ssid, password):
            if ssid == 'Missing':
                station.ssid, station.connected = ssid, False
            else:
                original_connect(ssid, password)

        with patch.object(station, 'connect', side_effect=connect):
            self.assertEqual(self.connect(), 'Second')
        self.assertEqual(self.clock, 15000)

    def test_driver_error_tries_next_network(self):
        station = self.network.station
        original_connect = station.connect

        def connect(ssid, password):
            if ssid == 'Missing':
                raise OSError('Connection rejected')
            original_connect(ssid, password)

        with patch.object(station, 'connect', side_effect=connect):
            self.assertEqual(self.connect(), 'Second')

    def test_all_unavailable_returns_offline_and_disconnects(self):
        self.network.available_ssids = set()
        self.assertFalse(self.connect())
        self.assertFalse(self.network.station.isconnected())
        self.assertIsNone(self.network.station.ssid)

    def test_empty_list_uses_legacy_credentials(self):
        self.namespace['WIFI_LIST'] = []
        with patch.object(self.network.station, 'connect', wraps=self.network.station.connect) as attempts:
            self.assertEqual(self.connect(), 'Second')
        attempts.assert_called_once_with('Second', 'legacy-password')
