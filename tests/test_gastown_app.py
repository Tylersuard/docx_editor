import tempfile
import unittest
from pathlib import Path

from gastown_app import Orchestrator, Role


class TestGasTownApp(unittest.TestCase):
    def test_seeded_flow(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "town.db"
            orch = Orchestrator(db)
            rig = orch.add_rig("r1", "/tmp/repo")
            polecat = orch.add_agent("p1", Role.POLECAT, rig_id=rig)
            orch.start_session(polecat)

            work = orch.create_work(
                title="Task",
                description="Do thing",
                scope="rig",
                rig_id=rig,
                kind="molecule",
            )
            orch.sling(work, polecat)
            orch.queue_merge(rig, work, "p1/task")

            processed = orch.run_refinery_patrol(rig)
            self.assertEqual(processed, 1)

            dashboard = orch.dashboard()
            self.assertEqual(len(dashboard["rigs"]), 1)
            self.assertGreaterEqual(len(dashboard["agents"]), 1)
            self.assertGreaterEqual(len(dashboard["recent_events"]), 1)

    def test_handoff_restarts_session(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "town.db"
            orch = Orchestrator(db)
            aid = orch.add_agent("deacon-1", Role.DEACON)
            first = orch.start_session(aid)
            second = orch.handoff(aid, reason="test")
            self.assertNotEqual(first.session_id, second.session_id)

            cur = orch.ledger.conn.cursor()
            running = cur.execute(
                "SELECT COUNT(*) AS c FROM sessions WHERE agent_id=? AND state='running'",
                (aid,),
            ).fetchone()["c"]
            ended = cur.execute(
                "SELECT COUNT(*) AS c FROM sessions WHERE agent_id=? AND state='ended'",
                (aid,),
            ).fetchone()["c"]
            self.assertEqual(running, 1)
            self.assertEqual(ended, 1)

    def test_run_prompt_autopilot(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "town.db"
            out_repo = Path(td) / "generated_app"
            orch = Orchestrator(db)
            result = orch.run_prompt(
                prompt="Build me a small cli that echoes input",
                repo_path=str(out_repo),
                rig_name="auto-rig",
            )
            self.assertIn("work_id", result)
            self.assertTrue((out_repo / "generated_program.py").exists())
            self.assertTrue((out_repo / "AUTOBUILDER_PROMPT.md").exists())
            self.assertTrue((out_repo / "README.generated.md").exists())


if __name__ == "__main__":
    unittest.main()
