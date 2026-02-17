import unittest
import inspect

from main import lifespan


class LifespanTests(unittest.TestCase):
    def test_lifespan_uses_asyncio_sleep_not_time_sleep(self):
        src = inspect.getsource(lifespan)
        # ensure no blocking time.sleep usage remains and that asyncio.sleep is present
        self.assertNotIn("time.sleep", src)
        self.assertIn("asyncio.sleep", src)


if __name__ == "__main__":
    unittest.main()
