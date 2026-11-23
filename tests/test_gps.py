import unittest

from gps import find_georgia_coordinates


class CoordinateTests(unittest.TestCase):
    def test_observed_formats(self):
        cases = [
            ("(33.8231,-84.2791)", "33.8231,-84.2791", "33.82310, -84.27910"),
            ("""33°46'42.2"N 84°24'07.8"W""", """33°46'42.2"N 84°24'07.8"W""", "33.77839, -84.40217"),
            (" 33.80549° N, 84.12826° W", "33.80549° N, 84.12826° W", "33.80549, -84.12826"),
            (" 33.8115352, -84.1308422", "33.8115352, -84.1308422", "33.81154, -84.13084"),
        ]
        for text, original, decimal in cases:
            with self.subTest(text=text):
                coords = find_georgia_coordinates(text)
                self.assertEqual(len(coords), 1)
                self.assertEqual(coords[0]["original"], original)
                self.assertEqual(coords[0]["decimal"], decimal)

    def test_unicode_dms(self):
        source = "33° 48′ 27.23″ N, 84° 7′ 43.46″ W"
        self.assertEqual(find_georgia_coordinates(source), [{
            "original": source,
            "decimal": "33.80756, -84.12874",
            "google_url": "https://maps.google.com/?q=33.80756,-84.12874",
            "apple_url": "https://maps.apple.com/?q=33.80756,-84.12874",
        }])

    def test_ascii_dms_and_decimal_remain_supported(self):
        text = """33° 48' 27.23" N, 84° 7' 43.46" W; 32.5, -83.5"""
        self.assertEqual(
            [coord["decimal"] for coord in find_georgia_coordinates(text)],
            ["33.80756, -84.12874", "32.50000, -83.50000"],
        )

    def test_unicode_dms_outside_georgia_is_not_relayed(self):
        self.assertEqual(
            find_georgia_coordinates("40° 48′ 27.23″ N, 84° 7′ 43.46″ W"),
            [],
        )


if __name__ == "__main__":
    unittest.main()
