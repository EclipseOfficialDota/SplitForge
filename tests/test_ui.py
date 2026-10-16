import tempfile
import unittest
from pathlib import Path

from textual.widgets import ContentSwitcher, DataTable

from splitforge.tui.app import SplitForgeApp
from splitforge.tui.screens.app_router import RouteSelector


class InterfaceTests(unittest.IsolatedAsyncioTestCase):
    async def test_navigation_and_route_modal_are_read_only_in_demo(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "absent-state.json"
            app = SplitForgeApp(state_path=state, demo=True)
            async with app.run_test(size=(140, 50)) as pilot:
                await pilot.pause()
                for _ in range(30):
                    if app.query_one("#health-table", DataTable).row_count == 2:
                        break
                    await pilot.pause(0.1)
                self.assertEqual(app.query_one("#health-table", DataTable).row_count, 2)
                for key, name in [("2", "router"), ("3", "profiles"), ("4", "browse"),
                                  ("5", "security"), ("6", "logs"), ("1", "home")]:
                    app.set_focus(None)
                    await pilot.press(key)
                    self.assertEqual(app.query_one(ContentSwitcher).current, name)
                app.action_navigate("router")
                app.query_one("#router-table", DataTable).focus()
                await pilot.press("enter")
                self.assertIsInstance(app.screen, RouteSelector)
                await pilot.click("#apply-route")
                await pilot.pause()
                self.assertFalse(app.busy)
                self.assertFalse(state.exists())

    async def test_compact_terminal_mounts(self):
        app = SplitForgeApp(demo=True)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            self.assertTrue(app.has_class("compact"))
            self.assertIsNotNone(app.query_one("#router-table", DataTable))


if __name__ == "__main__":
    unittest.main()
