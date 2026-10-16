import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from textual.widgets import Button, Checkbox, ContentSwitcher, DataTable, ProgressBar, Static

from splitforge.tui.app import SplitForgeApp
from splitforge.tui.screens.app_router import RouteSelector
from splitforge.tui.screens.help import CoreChecklist, GuideModal, LESSONS


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

    async def test_walkthrough_language_navigation_and_checklist_are_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "absent.json"
            app = SplitForgeApp(state_path=state, demo=True)
            with patch("splitforge.core.dependencies.install") as install, \
                 patch("splitforge.tui.screens.help.component_installed", return_value=False):
                async with app.run_test(size=(120, 40)) as pilot:
                    await pilot.pause()
                    await pilot.press("f1")
                    self.assertIsInstance(app.screen, GuideModal)
                    self.assertTrue(app.screen.query_one("#guide-back", Button).disabled)
                    await pilot.click("#guide-language")
                    self.assertEqual(app.screen.language, "fa")
                    for _ in range(len(LESSONS) - 1):
                        await pilot.click("#guide-next")
                        await pilot.pause(0.3)
                    self.assertEqual(app.screen.step, len(LESSONS) - 1)
                    self.assertTrue(app.screen.query_one("#guide-next", Button).disabled)
                    await pilot.click("#guide-cores")
                    await pilot.pause()
                    self.assertIsInstance(app.screen, CoreChecklist)
                    for box in app.screen.query(Checkbox):
                        box.value = False
                    app.screen.query_one("#core-dnstt-client", Checkbox).value = True
                    await pilot.pause()
                    self.assertEqual(app.screen.selected(), ["base", "xray", "tun2socks", "dnstt-client"])
                    await pilot.click("#cores-install")
                    await pilot.pause()
                    self.assertFalse(app.busy)
                    self.assertFalse(state.exists())
                    install.assert_not_called()

    async def test_batch_install_skips_present_tools_and_reports_partial_failure(self):
        app = SplitForgeApp(demo=True)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.demo = False
            with patch.object(app, "action_refresh"), patch.object(app, "load_journal"), \
                 patch("splitforge.core.dependencies.component_installed", side_effect=lambda name: name == "base"), \
                 patch("splitforge.core.dependencies.install", side_effect=[RuntimeError("simulated download failure"), "Installed openvpn"]) as install:
                app.install_cores(["wireguard", "openvpn"])
                for _ in range(30):
                    await pilot.pause(0.1)
                    if not app.busy:
                        break
                self.assertFalse(app.busy)
                self.assertEqual([call.args[0] for call in install.call_args_list], ["wireguard", "openvpn"])
                self.assertEqual(app.query_one("#dependency-progress", ProgressBar).progress, 3)
                self.assertIn("Failed: wireguard", str(app.query_one("#operation-status", Static).render()))
            app.demo = True

    async def test_checklist_can_be_cancelled_in_a_compact_terminal(self):
        app = SplitForgeApp(demo=True)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.press("f1")
            self.assertIsInstance(app.screen, GuideModal)
            await pilot.press("f2")
            self.assertIsInstance(app.screen, CoreChecklist)
            dialog = app.screen.query_one(".dialog")
            self.assertLessEqual(dialog.region.right, 80)
            self.assertLessEqual(dialog.region.bottom, 24)
            await pilot.press("escape")
            self.assertNotIsInstance(app.screen, CoreChecklist)


if __name__ == "__main__":
    unittest.main()
