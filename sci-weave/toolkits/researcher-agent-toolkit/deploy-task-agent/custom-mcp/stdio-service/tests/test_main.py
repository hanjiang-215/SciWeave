import unittest

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from main import main


class TemplateTests(unittest.TestCase):
    def test_template_entrypoint_exists(self) -> None:
        self.assertIsNone(main())


if __name__ == "__main__":
    unittest.main()
