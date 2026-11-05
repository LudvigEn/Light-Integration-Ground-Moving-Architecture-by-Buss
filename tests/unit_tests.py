"""Module for executing Unit-tests
"""
import unittest
import sys
from pathlib import Path
# Allow running this file directly from VS Code.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "project"))

import data # pylint: disable=import-error,wrong-import-position


class DataTests(unittest.TestCase):
    """Class for performing Data-tests"""
    def test_example(self): # Syntax for a test-example
        """Example-test: Tests if 2+2 = 4"""
        actual = 2+2 # What to test
        self.assertEqual(actual, 4) # Fails if it's not 4

    def test_receive_data(self):
        """Ensures that API returns data"""
        stop = data.read_data("740032188")
        self.assertIsNotNone(stop, "API returned no data")

# class AppTests(unittest.TestCase):
#     """Class for performing tests on Main-code"""
#     def test_example(self):
#         """Example-test: Does nothing"""
#         self.skipTest("Application tests are not implemented yet")

if __name__ == "__main__":
    unittest.main()
