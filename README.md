# Docx Editor + Multi-Agent Orchestration MVP

This repository now contains two tools:

1. **`docx_revision.py`**: a helper for tracked changes in `.docx` files.
2. **`gastown_app.py`**: a Gas Town–style multi-agent orchestration MVP (CLI-first), inspired by the requirements in your spec.

---

## Orchestration App (`gastown_app.py`)

### What it implements

The app provides a practical v1 control-plane model with durable state:

- **Town + Rig model** (global and project scope)
- **Persistent agent identities** and ephemeral runtime sessions
- **Durable work ledger** (SQLite) with persistent and ephemeral work objects
- **Role-based agents** (`mayor`, `polecat`, `refinery`, `witness`, `deacon`, `dog`, `boot`, `crew`, `operator`)
- **Sling/nudge/handoff** operations
- **Convoy tracking**
- **Merge queue processing** with a refinery patrol
- **Witness/Deacon/Boot patrol loops**
- **Dashboard feed** showing current state and recent activity

### Data model highlights

The ledger stores:

- `rigs`
- `agents`
- `sessions`
- `work_items` (beads/molecules/gates/wisps via `kind` + `persistent` flag)
- `messages`
- `history` (audit log)
- `convoys`
- `merge_queue`

### Run

```bash
python3 gastown_app.py --db town.db init
python3 gastown_app.py --db town.db seed
python3 gastown_app.py --db town.db patrol
python3 gastown_app.py --db town.db dashboard
```

`seed` means **seed demo data** (sample rig, agents, work, convoy, merge item) so you can see the system behavior immediately. It is not a numeric random seed.

### Tell agents to write a program (manual flow)

The manual flow below gives you full control over work routing.

### One-shot autopilot flow (what you asked for)

You can now enter one prompt and let the app handle rig/agent/work setup automatically:

```bash
python3 gastown_app.py --db town.db run-prompt \
  --prompt "Please build me a CLI program that validates CSV files and reports errors" \
  --repo-path /tmp/my_generated_app
```

What this command does:

- creates or reuses a rig
- creates or reuses mayor/polecat/refinery/witness agents
- creates work + convoy
- slings work to the polecat worker
- materializes generated starter program files in `--repo-path`
- queues and processes merge for the generated work item

You can inspect results with:

```bash
python3 gastown_app.py --db town.db dashboard
```

### Manual flow (explicit operator control)

A practical command flow is:

```bash
# 1) Initialize
python3 gastown_app.py --db town.db init

# 2) Register your project and workers
python3 gastown_app.py --db town.db add-rig --name app --repo-path /path/to/repo
python3 gastown_app.py --db town.db add-agent --name mayor --role mayor --start-session
python3 gastown_app.py --db town.db add-agent --name polecat-1 --role polecat --start-session

# 3) Inspect ids you just created
python3 gastown_app.py --db town.db list-agents

# 4) Create work request for the coding worker
python3 gastown_app.py --db town.db create-work \
  --scope town \
  --kind molecule \
  --title "Build REST TODO API in FastAPI" \
  --description "Implement CRUD endpoints, tests, and README docs"

# 5) Find work id and assign (sling) to the worker
python3 gastown_app.py --db town.db list-work
python3 gastown_app.py --db town.db sling --work-id <WORK_ID> --agent-id <POLECAT_AGENT_ID>

# 6) Run patrol loop and inspect progress
python3 gastown_app.py --db town.db patrol
python3 gastown_app.py --db town.db dashboard
```

### Notes on spec mapping

- **Identity vs session**: `agents` are durable; `sessions` are disposable and restartable.
- **Workflow durability**: work is persisted in SQLite and survives process restarts.
- **Wisps/ephemeral work**: `work_items.persistent = 0` allows orchestration-only temporary tasks.
- **Gates/wait states**: represented with `kind="gate"` and status fields, ready for callback resumption logic.
- **Cross-rig readiness**: work is namespaced by rig; town-scope work is supported.
- **Completion-oriented**: patrol and merge flow moves work toward `done`, not process uptime.

---

## Docx Revision Helper (`docx_revision.py`)

Basic usage:

```python
from docx_revision import DocxRevisionEditor

editor = DocxRevisionEditor('input.docx')
editor.add_text(0, 'Inserted text', author='Alice')
editor.delete_text('target', author='Alice')
editor.highlight_text('highlight me', color='yellow', author='Alice')
editor.add_comment('highlight me', 'My comment', author='Alice')
editor.save('output.docx')
```

All changes are written as WordprocessingML elements (`w:ins`, `w:del`, comments, etc.) so Microsoft Word displays them as standard revisions.
