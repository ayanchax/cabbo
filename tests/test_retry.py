import unittest

from test_temp_trip_cleanup import ROOT
from utils.retry import get_retry_delay_seconds


class RetryTests(unittest.TestCase):
    def test_exponential_delays_and_cap(self):
        self.assertEqual([get_retry_delay_seconds(n) for n in range(1, 8)],
                         [60, 120, 240, 480, 900, 900, 900])

    def test_large_attempt_does_not_compute_an_unbounded_power(self):
        self.assertEqual(get_retry_delay_seconds(10 ** 100), 900)

    def test_nonpositive_count_uses_initial_delay(self):
        self.assertEqual(get_retry_delay_seconds(0), 60)
        self.assertEqual(get_retry_delay_seconds(-5), 60)
