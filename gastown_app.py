#!/usr/bin/env python3
"""Gas Town-style multi-agent orchestration MVP.

This is a CLI-first orchestration framework with:
- Town/Rig scopes
- Persistent agent identities + ephemeral sessions
- Durable work ledger (SQLite)
- Convoys + merge queue
- Sling/nudge/handoff operations
- Patrol loops (deacon/witness/refinery/boot)

It intentionally provides v1 primitives that can be extended with AutoGen runtime adapters.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
import re
from typing import Any, Dict, List, Optional


class Role(str, Enum):
    OPERATOR = "operator"
    MAYOR = "mayor"
    POLECAT = "polecat"
    REFINERY = "refinery"
    WITNESS = "witness"
    DEACON = "deacon"
    DOG = "dog"
    BOOT = "boot"
    CREW = "crew"


class WorkStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    WAITING_GATE = "waiting_gate"
    DONE = "done"
    FAILED = "failed"


@dataclass
class RuntimeSession:
    session_id: str
    agent_id: str
    started_at: str
    state: str = "running"


class Ledger:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        cur = self.conn.cursor()
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS rigs (
                id TEXT PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                repo_path TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS agents (
                id TEXT PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                role TEXT NOT NULL,
                rig_id TEXT,
                admin_state TEXT NOT NULL,
                hook_work_id TEXT,
                metadata_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (rig_id) REFERENCES rigs(id)
            );

            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                state TEXT NOT NULL,
                FOREIGN KEY (agent_id) REFERENCES agents(id)
            );

            CREATE TABLE IF NOT EXISTS work_items (
                id TEXT PRIMARY KEY,
                scope TEXT NOT NULL,
                rig_id TEXT,
                kind TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                status TEXT NOT NULL,
                assignee_agent_id TEXT,
                parent_id TEXT,
                deps_json TEXT NOT NULL,
                labels_json TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                persistent INTEGER NOT NULL,
                gate_key TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                sender_agent_id TEXT,
                recipient_agent_id TEXT NOT NULL,
                body TEXT NOT NULL,
                created_at TEXT NOT NULL,
                related_work_id TEXT
            );

            CREATE TABLE IF NOT EXISTS history (
                id TEXT PRIMARY KEY,
                object_type TEXT NOT NULL,
                object_id TEXT NOT NULL,
                event TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS convoys (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                status TEXT NOT NULL,
                work_ids_json TEXT NOT NULL,
                participants_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS merge_queue (
                id TEXT PRIMARY KEY,
                rig_id TEXT NOT NULL,
                work_id TEXT NOT NULL,
                branch TEXT NOT NULL,
                status TEXT NOT NULL,
                attempt_count INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        self.conn.commit()

    @staticmethod
    def now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def uid(prefix: str) -> str:
        return f"{prefix}_{uuid.uuid4().hex[:10]}"

    def add_history(self, object_type: str, object_id: str, event: str, payload: Dict[str, Any]) -> None:
        self.conn.execute(
            "INSERT INTO history (id, object_type, object_id, event, payload_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (self.uid("hist"), object_type, object_id, event, json.dumps(payload), self.now()),
        )
        self.conn.commit()


class Orchestrator:
    def __init__(self, db_path: Path = Path("town.db")):
        self.ledger = Ledger(db_path)

    def add_rig(self, name: str, repo_path: str) -> str:
        rid = self.ledger.uid("rig")
        self.ledger.conn.execute(
            "INSERT INTO rigs (id, name, repo_path, created_at) VALUES (?, ?, ?, ?)",
            (rid, name, repo_path, self.ledger.now()),
        )
        self.ledger.conn.commit()
        self.ledger.add_history("rig", rid, "created", {"name": name, "repo_path": repo_path})
        return rid

    def add_agent(self, name: str, role: Role, rig_id: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> str:
        aid = self.ledger.uid("agent")
        self.ledger.conn.execute(
            """
            INSERT INTO agents (id, name, role, rig_id, admin_state, hook_work_id, metadata_json, created_at)
            VALUES (?, ?, ?, ?, 'active', NULL, ?, ?)
            """,
            (aid, name, role.value, rig_id, json.dumps(metadata or {}), self.ledger.now()),
        )
        self.ledger.conn.commit()
        self.ledger.add_history("agent", aid, "created", {"name": name, "role": role.value})
        return aid

    def start_session(self, agent_id: str) -> RuntimeSession:
        sid = self.ledger.uid("sess")
        now = self.ledger.now()
        self.ledger.conn.execute(
            "INSERT INTO sessions (id, agent_id, started_at, state) VALUES (?, ?, ?, 'running')",
            (sid, agent_id, now),
        )
        self.ledger.conn.commit()
        self.ledger.add_history("agent", agent_id, "session_started", {"session_id": sid})
        return RuntimeSession(session_id=sid, agent_id=agent_id, started_at=now)

    def create_work(
        self,
        title: str,
        description: str,
        scope: str = "town",
        rig_id: Optional[str] = None,
        kind: str = "bead",
        labels: Optional[List[str]] = None,
        parent_id: Optional[str] = None,
        deps: Optional[List[str]] = None,
        persistent: bool = True,
    ) -> str:
        wid = self.ledger.uid("work")
        now = self.ledger.now()
        self.ledger.conn.execute(
            """
            INSERT INTO work_items
            (id, scope, rig_id, kind, title, description, status, assignee_agent_id, parent_id, deps_json, labels_json, payload_json, persistent, gate_key, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 'pending', NULL, ?, ?, ?, '{}', ?, NULL, ?, ?)
            """,
            (wid, scope, rig_id, kind, title, description, parent_id, json.dumps(deps or []), json.dumps(labels or []), 1 if persistent else 0, now, now),
        )
        self.ledger.conn.commit()
        self.ledger.add_history("work", wid, "created", {"kind": kind, "scope": scope, "title": title})
        return wid

    def sling(self, work_id: str, agent_id: str, start_now: bool = True, force_restart: bool = False) -> None:
        cur = self.ledger.conn.cursor()
        cur.execute("UPDATE agents SET hook_work_id=? WHERE id=?", (work_id, agent_id))
        cur.execute(
            "UPDATE work_items SET assignee_agent_id=?, status='in_progress', updated_at=? WHERE id=?",
            (agent_id, self.ledger.now(), work_id),
        )
        self.ledger.conn.commit()
        self.ledger.add_history("work", work_id, "slung", {"agent_id": agent_id, "start_now": start_now, "force_restart": force_restart})
        if start_now:
            if force_restart:
                self.handoff(agent_id, reason="forced_restart_before_resumption")
            else:
                self.nudge(agent_id)

    def nudge(self, agent_id: str) -> None:
        self.ledger.add_history("agent", agent_id, "nudged", {})

    def handoff(self, agent_id: str, reason: str = "self_handoff") -> RuntimeSession:
        cur = self.ledger.conn.cursor()
        cur.execute(
            "UPDATE sessions SET state='ended', ended_at=? WHERE agent_id=? AND state='running'",
            (self.ledger.now(), agent_id),
        )
        self.ledger.conn.commit()
        self.ledger.add_history("agent", agent_id, "handoff", {"reason": reason})
        return self.start_session(agent_id)

    def create_convoy(self, title: str, work_ids: List[str], participants: Optional[List[str]] = None) -> str:
        cid = self.ledger.uid("convoy")
        now = self.ledger.now()
        self.ledger.conn.execute(
            "INSERT INTO convoys (id, title, status, work_ids_json, participants_json, created_at, updated_at) VALUES (?, ?, 'active', ?, ?, ?, ?)",
            (cid, title, json.dumps(work_ids), json.dumps(participants or []), now, now),
        )
        self.ledger.conn.commit()
        self.ledger.add_history("convoy", cid, "created", {"work_count": len(work_ids)})
        return cid

    def queue_merge(self, rig_id: str, work_id: str, branch: str) -> str:
        mid = self.ledger.uid("merge")
        now = self.ledger.now()
        self.ledger.conn.execute(
            "INSERT INTO merge_queue (id, rig_id, work_id, branch, status, attempt_count, created_at, updated_at) VALUES (?, ?, ?, ?, 'queued', 0, ?, ?)",
            (mid, rig_id, work_id, branch, now, now),
        )
        self.ledger.conn.commit()
        self.ledger.add_history("merge", mid, "queued", {"work_id": work_id, "branch": branch})
        return mid

    def run_refinery_patrol(self, rig_id: str) -> int:
        cur = self.ledger.conn.cursor()
        rows = cur.execute(
            "SELECT * FROM merge_queue WHERE rig_id=? AND status='queued' ORDER BY created_at ASC",
            (rig_id,),
        ).fetchall()
        processed = 0
        for row in rows:
            cur.execute("UPDATE merge_queue SET status='merged', attempt_count=attempt_count+1, updated_at=? WHERE id=?", (self.ledger.now(), row["id"]))
            cur.execute("UPDATE work_items SET status='done', updated_at=? WHERE id=?", (self.ledger.now(), row["work_id"]))
            self.ledger.add_history("merge", row["id"], "merged", {"work_id": row["work_id"]})
            processed += 1
        self.ledger.conn.commit()
        return processed

    def run_witness_patrol(self, rig_id: str) -> Dict[str, int]:
        cur = self.ledger.conn.cursor()
        stuck = cur.execute(
            "SELECT COUNT(*) AS c FROM work_items WHERE rig_id=? AND status IN ('in_progress','waiting_gate')",
            (rig_id,),
        ).fetchone()["c"]
        queued = cur.execute("SELECT COUNT(*) AS c FROM merge_queue WHERE rig_id=? AND status='queued'", (rig_id,)).fetchone()["c"]
        self.ledger.add_history("rig", rig_id, "witness_patrol", {"stuck_or_active": stuck, "queued_merges": queued})
        return {"stuck_or_active": stuck, "queued_merges": queued}

    def run_deacon_patrol(self) -> Dict[str, int]:
        cur = self.ledger.conn.cursor()
        rigs = cur.execute("SELECT id FROM rigs").fetchall()
        work_pending = cur.execute("SELECT COUNT(*) AS c FROM work_items WHERE status='pending'").fetchone()["c"]
        self.ledger.add_history("town", "town", "deacon_patrol", {"rig_count": len(rigs), "pending": work_pending})
        return {"rig_count": len(rigs), "pending": work_pending}

    def run_boot_watchdog(self) -> Dict[str, int]:
        cur = self.ledger.conn.cursor()
        running_deacons = cur.execute(
            """
            SELECT COUNT(*) AS c
            FROM sessions s JOIN agents a ON a.id=s.agent_id
            WHERE a.role='deacon' AND s.state='running'
            """
        ).fetchone()["c"]
        if running_deacons == 0:
            self.ledger.add_history("town", "town", "boot_watchdog", {"action": "nudge_or_restart_deacon"})
        else:
            self.ledger.add_history("town", "town", "boot_watchdog", {"action": "healthy"})
        return {"running_deacons": running_deacons}

    def dashboard(self) -> Dict[str, Any]:
        cur = self.ledger.conn.cursor()
        return {
            "rigs": [dict(r) for r in cur.execute("SELECT * FROM rigs ORDER BY created_at DESC")],
            "agents": [dict(r) for r in cur.execute("SELECT * FROM agents ORDER BY created_at DESC")],
            "active_convoys": [dict(r) for r in cur.execute("SELECT * FROM convoys WHERE status='active'")],
            "merge_queue": [dict(r) for r in cur.execute("SELECT * FROM merge_queue WHERE status='queued' ORDER BY created_at")],
            "recent_events": [dict(r) for r in cur.execute("SELECT * FROM history ORDER BY created_at DESC LIMIT 25")],
        }

    def get_or_create_rig(self, name: str, repo_path: str) -> str:
        cur = self.ledger.conn.cursor()
        row = cur.execute("SELECT id FROM rigs WHERE name=?", (name,)).fetchone()
        if row:
            return row["id"]
        return self.add_rig(name, repo_path)

    def get_or_create_agent(self, name: str, role: Role, rig_id: Optional[str] = None, start_session: bool = True) -> str:
        cur = self.ledger.conn.cursor()
        row = cur.execute("SELECT id FROM agents WHERE name=?", (name,)).fetchone()
        if row:
            aid = row["id"]
        else:
            aid = self.add_agent(name, role, rig_id=rig_id)
        if start_session:
            running = cur.execute(
                "SELECT COUNT(*) AS c FROM sessions WHERE agent_id=? AND state='running'",
                (aid,),
            ).fetchone()["c"]
            if running == 0:
                self.start_session(aid)
        return aid

    def _slug(self, text: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
        return slug[:40] or "project"

    def _materialize_program(self, prompt: str, repo_path: str) -> List[str]:
        repo = Path(repo_path)
        repo.mkdir(parents=True, exist_ok=True)
        created = []

        prompt_file = repo / "AUTOBUILDER_PROMPT.md"
        prompt_file.write_text(f"# Build prompt\n\n{prompt}\n", encoding="utf-8")
        created.append(str(prompt_file))

        app_file = repo / "generated_program.py"
        app_file.write_text(
            (
                '"""Auto-generated starter program from orchestration prompt."""\n\n'
                "import argparse\n\n\n"
                "def run() -> None:\n"
                "    parser = argparse.ArgumentParser(description='Generated program scaffold')\n"
                "    parser.add_argument('--input', default='')\n"
                "    args = parser.parse_args()\n"
                "    print('Prompt goal:')\n"
                f"    print({prompt!r})\n"
                "    print('Received input:', args.input)\n\n\n"
                "if __name__ == '__main__':\n"
                "    run()\n"
            ),
            encoding="utf-8",
        )
        created.append(str(app_file))

        readme_file = repo / "README.generated.md"
        readme_file.write_text(
            (
                "# Generated Program\n\n"
                "This scaffold was produced by `gastown_app.py run-prompt`.\n\n"
                "## Run\n\n"
                "```bash\npython3 generated_program.py --input 'demo'\n```\n"
            ),
            encoding="utf-8",
        )
        created.append(str(readme_file))
        return created

    def run_prompt(self, prompt: str, repo_path: str, rig_name: Optional[str] = None) -> Dict[str, Any]:
        rig_name = rig_name or f"rig-{self._slug(prompt)}"
        rig_id = self.get_or_create_rig(rig_name, repo_path)
        mayor_id = self.get_or_create_agent("mayor-auto", Role.MAYOR, start_session=True)
        polecat_id = self.get_or_create_agent(f"polecat-{self._slug(rig_name)}", Role.POLECAT, rig_id=rig_id, start_session=True)
        refinery_id = self.get_or_create_agent(f"refinery-{self._slug(rig_name)}", Role.REFINERY, rig_id=rig_id, start_session=True)
        witness_id = self.get_or_create_agent(f"witness-{self._slug(rig_name)}", Role.WITNESS, rig_id=rig_id, start_session=True)

        work_id = self.create_work(
            title=f"Build program: {prompt[:80]}",
            description=prompt,
            scope="rig",
            rig_id=rig_id,
            kind="molecule",
            labels=["autoprompt", "generated"],
        )
        convoy_id = self.create_convoy(
            title=f"Auto convoy for: {prompt[:40]}",
            work_ids=[work_id],
            participants=[mayor_id, polecat_id, refinery_id, witness_id],
        )
        self.sling(work_id, polecat_id, start_now=True)
        created_files = self._materialize_program(prompt, repo_path)
        merge_id = self.queue_merge(rig_id, work_id, f"{polecat_id}/auto-{self._slug(prompt)}")
        self.run_refinery_patrol(rig_id)
        self.run_witness_patrol(rig_id)
        self.run_deacon_patrol()

        self.ledger.add_history("work", work_id, "autobuilder_materialized", {"files": created_files})
        return {
            "rig_id": rig_id,
            "work_id": work_id,
            "convoy_id": convoy_id,
            "merge_id": merge_id,
            "assigned_agent_id": polecat_id,
            "created_files": created_files,
        }


def cmd_init(args: argparse.Namespace) -> None:
    orch = Orchestrator(Path(args.db))
    print(f"Initialized town ledger at {orch.ledger.db_path}")


def cmd_seed(args: argparse.Namespace) -> None:
    orch = Orchestrator(Path(args.db))
    rig = orch.add_rig("sample-rig", "./")
    mayor = orch.add_agent("mayor", Role.MAYOR)
    deacon = orch.add_agent("deacon", Role.DEACON)
    refinery = orch.add_agent("refinery", Role.REFINERY, rig_id=rig)
    witness = orch.add_agent("witness", Role.WITNESS, rig_id=rig)
    polecat = orch.add_agent("polecat-1", Role.POLECAT, rig_id=rig)
    orch.start_session(mayor)
    orch.start_session(deacon)
    orch.start_session(refinery)
    orch.start_session(witness)
    orch.start_session(polecat)

    w1 = orch.create_work(
        title="Implement feature X",
        description="Create implementation and tests",
        scope="rig",
        rig_id=rig,
        kind="molecule",
        labels=["feature", "priority:high"],
    )
    w2 = orch.create_work(
        title="CI gate",
        description="Wait for CI callback",
        scope="rig",
        rig_id=rig,
        kind="gate",
        parent_id=w1,
        persistent=False,
    )
    orch.sling(w1, polecat, start_now=True)
    orch.create_convoy("Feature X Convoy", [w1, w2], participants=[polecat, refinery, witness])
    orch.queue_merge(rig, w1, "polecat-1/feature-x")
    print("Seeded sample town, rig, agents, work, and convoy")


def cmd_patrol(args: argparse.Namespace) -> None:
    orch = Orchestrator(Path(args.db))
    town = orch.run_deacon_patrol()
    boot = orch.run_boot_watchdog()
    cur = orch.ledger.conn.cursor()
    rigs = [r["id"] for r in cur.execute("SELECT id FROM rigs")]
    for rig_id in rigs:
        witness = orch.run_witness_patrol(rig_id)
        merges = orch.run_refinery_patrol(rig_id)
        print(f"rig={rig_id} witness={witness} refinery_processed={merges}")
    print(f"town={town} boot={boot}")


def cmd_dashboard(args: argparse.Namespace) -> None:
    orch = Orchestrator(Path(args.db))
    print(json.dumps(orch.dashboard(), indent=2))


def cmd_add_rig(args: argparse.Namespace) -> None:
    orch = Orchestrator(Path(args.db))
    rid = orch.add_rig(args.name, args.repo_path)
    print(json.dumps({"rig_id": rid, "name": args.name, "repo_path": args.repo_path}, indent=2))


def cmd_add_agent(args: argparse.Namespace) -> None:
    orch = Orchestrator(Path(args.db))
    role = Role(args.role)
    aid = orch.add_agent(args.name, role, rig_id=args.rig_id)
    if args.start_session:
        session = orch.start_session(aid)
    else:
        session = None
    print(json.dumps({"agent_id": aid, "name": args.name, "role": role.value, "session": session.__dict__ if session else None}, indent=2))


def cmd_create_work(args: argparse.Namespace) -> None:
    orch = Orchestrator(Path(args.db))
    labels = [s.strip() for s in args.labels.split(",")] if args.labels else []
    wid = orch.create_work(
        title=args.title,
        description=args.description,
        scope=args.scope,
        rig_id=args.rig_id,
        kind=args.kind,
        labels=labels,
        parent_id=args.parent_id,
        deps=args.deps,
        persistent=not args.ephemeral,
    )
    print(json.dumps({"work_id": wid, "title": args.title, "scope": args.scope, "kind": args.kind}, indent=2))


def cmd_sling(args: argparse.Namespace) -> None:
    orch = Orchestrator(Path(args.db))
    orch.sling(args.work_id, args.agent_id, start_now=not args.defer, force_restart=args.force_restart)
    print(json.dumps({"status": "ok", "work_id": args.work_id, "agent_id": args.agent_id}, indent=2))


def cmd_list_agents(args: argparse.Namespace) -> None:
    orch = Orchestrator(Path(args.db))
    cur = orch.ledger.conn.cursor()
    rows = [dict(r) for r in cur.execute("SELECT * FROM agents ORDER BY created_at DESC")]
    print(json.dumps(rows, indent=2))


def cmd_list_work(args: argparse.Namespace) -> None:
    orch = Orchestrator(Path(args.db))
    cur = orch.ledger.conn.cursor()
    rows = [dict(r) for r in cur.execute("SELECT * FROM work_items ORDER BY created_at DESC")]
    print(json.dumps(rows, indent=2))


def cmd_run_prompt(args: argparse.Namespace) -> None:
    orch = Orchestrator(Path(args.db))
    summary = orch.run_prompt(prompt=args.prompt, repo_path=args.repo_path, rig_name=args.rig_name)
    print(json.dumps(summary, indent=2))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Gas Town-style orchestration MVP")
    p.add_argument("--db", default="town.db", help="SQLite ledger path")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("init", help="Initialize ledger")
    sp.set_defaults(fn=cmd_init)

    sp = sub.add_parser("seed", help="Seed sample rig/town")
    sp.set_defaults(fn=cmd_seed)

    sp = sub.add_parser("patrol", help="Run one patrol cycle")
    sp.set_defaults(fn=cmd_patrol)

    sp = sub.add_parser("dashboard", help="Show JSON dashboard")
    sp.set_defaults(fn=cmd_dashboard)

    sp = sub.add_parser("add-rig", help="Add a rig/project to the town")
    sp.add_argument("--name", required=True, help="Rig name")
    sp.add_argument("--repo-path", required=True, help="Repository path")
    sp.set_defaults(fn=cmd_add_rig)

    sp = sub.add_parser("add-agent", help="Add a persistent agent identity")
    sp.add_argument("--name", required=True, help="Agent name")
    sp.add_argument("--role", required=True, choices=[r.value for r in Role], help="Agent role")
    sp.add_argument("--rig-id", default=None, help="Optional rig id for rig-scoped agents")
    sp.add_argument("--start-session", action="store_true", help="Start runtime session immediately")
    sp.set_defaults(fn=cmd_add_agent)

    sp = sub.add_parser("create-work", help="Create a work item (bead/molecule/gate/wisp)")
    sp.add_argument("--title", required=True, help="Work title")
    sp.add_argument("--description", required=True, help="Work description")
    sp.add_argument("--scope", default="town", choices=["town", "rig"], help="Work scope")
    sp.add_argument("--rig-id", default=None, help="Rig id (required when scope=rig)")
    sp.add_argument("--kind", default="bead", help="Work kind (bead/molecule/gate/wisp/etc.)")
    sp.add_argument("--labels", default="", help="Comma-separated labels")
    sp.add_argument("--parent-id", default=None, help="Optional parent work id")
    sp.add_argument("--deps", nargs="*", default=None, help="Optional dependency work ids")
    sp.add_argument("--ephemeral", action="store_true", help="Mark work as non-persistent")
    sp.set_defaults(fn=cmd_create_work)

    sp = sub.add_parser("sling", help="Assign work to agent hook")
    sp.add_argument("--work-id", required=True, help="Work id to route")
    sp.add_argument("--agent-id", required=True, help="Agent id to receive work")
    sp.add_argument("--defer", action="store_true", help="Attach but do not start immediately")
    sp.add_argument("--force-restart", action="store_true", help="Force handoff/restart before resumption")
    sp.set_defaults(fn=cmd_sling)

    sp = sub.add_parser("list-agents", help="List known agent identities")
    sp.set_defaults(fn=cmd_list_agents)

    sp = sub.add_parser("list-work", help="List known work items")
    sp.set_defaults(fn=cmd_list_work)

    sp = sub.add_parser("run-prompt", help="One-shot autopilot: create agents/work and execute prompt")
    sp.add_argument("--prompt", required=True, help="Program request, e.g. 'build me X'")
    sp.add_argument("--repo-path", required=True, help="Directory where generated program files are written")
    sp.add_argument("--rig-name", default=None, help="Optional rig name (auto-derived when omitted)")
    sp.set_defaults(fn=cmd_run_prompt)
    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
