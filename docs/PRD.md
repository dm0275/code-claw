# 📄 1. PRODUCT REQUIREMENTS DOCUMENT (PRD)

## 1. Product Name

**CodeClaw**
*Tagline: “Your remote coding agent powered by Codex CLI.”*

---

## 2. Problem Statement

Developers want to leverage powerful coding agents like Codex CLI, but:

* They are **terminal-bound**
* Lack **task management, visibility, and history**
* Provide **no multi-user or remote access**
* Have **limited safety controls**
* Are **not integrated into modern workflows (UI, chat, approvals)**

---

## 3. Solution Overview

Build a **web-first orchestration platform** that:

* Accepts natural language coding tasks
* Executes them using **Codex CLI in controlled environments**
* Streams progress in real-time
* Produces structured outputs (diffs, summaries, logs)
* Enforces safety and approval workflows

---

## 4. Target Users

### Primary

* Individual developers (like you)
* AI/Platform engineers
* DevOps / AIOps engineers

### Secondary (future)

* Small teams
* Internal engineering platforms

---

## 5. Core Value Proposition

| Feature                  | Value                                   |
|--------------------------|-----------------------------------------|
| Codex CLI orchestration  | No need to manually run terminal agents |
| Web UI + history         | Visibility + reproducibility            |
| Diff + approval workflow | Safe AI-assisted coding                 |
| Workspace isolation      | Prevents repo corruption                |
| Structured prompting     | Better outputs than raw CLI             |

---

## 6. User Stories (v1)

### Workspace

* As a user, I can register a repo or local workspace
* As a user, I can select a workspace before running tasks

### Task Execution

* As a user, I can submit a natural-language coding task
* As a user, I can see live logs of execution
* As a user, I can see which files were modified

### Review & Approval

* As a user, I can view diffs before applying changes
* As a user, I can approve or reject changes

### History

* As a user, I can view past tasks and outputs

---

## 7. Functional Requirements

### 7.1 Task Management

* Create task
* Track status: `pending → running → awaiting_approval → completed/failed`
* Attach workspace

### 7.2 Codex Execution

* Run Codex CLI in specified directory
* Pass structured prompt
* Capture:

    * stdout
    * stderr
    * exit code

### 7.3 Output Processing

* Extract:

    * file diffs
    * summaries
    * logs
* Store artifacts

### 7.4 Approval System

* Require approval before:

    * applying changes
    * committing
* Allow:

    * approve
    * reject
    * request re-run (future)

### 7.5 Workspace Management

* Register repo (local path or git clone)
* Create per-task branch/sandbox
* Cleanup after task

### 7.6 Streaming

* Real-time logs via WebSockets or SSE

---

## 8. Non-Functional Requirements

| Category      | Requirement                         |
|---------------|-------------------------------------|
| Performance   | <1s task start latency              |
| Reliability   | tasks should recover/log on failure |
| Security      | restrict filesystem + commands      |
| Scalability   | support multiple concurrent tasks   |
| Observability | logs + metrics                      |

---

## 9. Out of Scope (v1)

* Voice interface
* Slack/Discord integration
* Autonomous agents
* Multi-agent orchestration
* GitHub PR automation
* Long-term semantic memory

---

## 10. Success Metrics

* % tasks successfully completed
* average task duration
* user approvals vs rejections
* repeat usage (daily active use)
* number of tasks per workspace

---

# 🏗️ 2. ARCHITECTURE DOCUMENT

## 1. High-Level Architecture

```text
        ┌──────────────┐
        │   Web UI     │
        └──────┬───────┘
               │
        ┌──────▼───────┐
        │   API Layer  │
        └──────┬───────┘
               │
        ┌──────▼────────────┐
        │   Orchestrator    │
        └──────┬────────────┘
               │
     ┌─────────▼─────────┐
     │   Executor Layer   │
     │   (Codex Runner)  │
     └─────────┬─────────┘
               │
        ┌──────▼───────┐
        │ Workspace FS │
        └──────────────┘
```

---

## 2. Components

### 2.1 API Layer (FastAPI)

Responsibilities:

* REST endpoints
* auth (future)
* task lifecycle
* streaming endpoint

---

### 2.2 Orchestrator

Core logic layer.

Responsibilities:

* build structured prompt
* select workspace
* apply policies
* manage task state
* call executor

---

### 2.3 Executor (Codex Runner)

Thin wrapper around Codex CLI.

Responsibilities:

* spawn process
* pass flags
* capture logs
* emit events

Example:

```bash
codex --prompt "..." --json
```

---

### 2.4 Workspace Manager

Responsibilities:

* clone repos
* checkout branches
* isolate per task
* cleanup

---

### 2.5 Storage

#### Postgres

* users
* workspaces
* tasks
* runs
* approvals

#### File Storage

* logs
* diffs
* artifacts

---

### 2.6 Streaming Layer

Options:

* SSE (simpler)
* WebSockets (more flexible)

Used for:

* logs
* status updates

---

### 2.7 Policy Engine

Controls:

* allowed directories
* allowed commands
* max runtime
* approval triggers

---

## 3. Data Model

### Task

```json
{
  "id": "uuid",
  "workspace_id": "uuid",
  "prompt": "string",
  "status": "running",
  "created_at": "...",
  "completed_at": "..."
}
```

### Run

```json
{
  "id": "uuid",
  "task_id": "uuid",
  "cwd": "/workspace/repo",
  "exit_code": 0,
  "stdout_path": "...",
  "stderr_path": "..."
}
```

---

## 4. Execution Flow

### Step-by-step

1. User submits task
2. API creates Task record
3. Orchestrator:

    * builds structured prompt
    * prepares workspace
4. Executor:

    * launches Codex CLI
5. Streaming:

    * logs pushed to UI
6. Codex completes
7. System extracts:

    * diffs
    * summary
8. Approval required
9. User approves/rejects
10. Task finalized

---

## 5. Prompt Construction Layer

Example structure:

```text
OBJECTIVE:
Add pagination to endpoint...

CONSTRAINTS:
- Only modify /services/orders
- Do not add dependencies

ACCEPTANCE CRITERIA:
- Tests pass
- Add new tests

OUTPUT:
- Summary
- List of files changed
```

---

## 6. Isolation Strategy

### v1

* local execution
* per-task branch

### v2

* Docker container per task

---

## 7. Security Model

* directory allowlist
* no root access
* restrict shell commands
* secrets masking
* approval gates

---

# 🗺️ 3. MILESTONE ROADMAP

---

## 🚀 Phase 0 — Spike (1–3 days)

Goal: Prove Codex CLI integration

Deliverables:

* Python script:

    * run Codex CLI
    * capture output
* test on real repo

Success:

* can modify a file
* can explain repo

---

## 🧱 Phase 1 — Core Backend (1–2 weeks)

Goal: Build minimal backend

Deliverables:

* FastAPI app
* Task + Run models
* Codex runner service
* basic prompt builder

Success:

* API can trigger Codex tasks

---

## 🌐 Phase 2 — Web UI + Streaming (1–2 weeks)

Goal: usable interface

Deliverables:

* Next.js UI
* task submission page
* live logs (SSE)
* task history page

Success:

* end-to-end flow works

---

## 🔍 Phase 3 — Diff + Artifacts (1 week)

Goal: make output useful

Deliverables:

* diff extraction
* diff viewer
* artifact storage

Success:

* user can review changes

---

## ✅ Phase 4 — Approval System (1 week)

Goal: safety

Deliverables:

* approval UI
* approval API
* gating logic

Success:

* no changes applied without approval

---

## 🐳 Phase 5 — Isolation (1–2 weeks)

Goal: production safety

Deliverables:

* Docker worker
* per-task container
* workspace mounting

Success:

* safe execution environment

---

## 🔁 Phase 6 — Polish (ongoing)

* retry tasks
* better prompts
* performance tuning
* UX improvements

---

# 🔥 Bonus: What Makes This Actually Valuable

The real differentiation is NOT:

* “we run Codex”

It’s:

* structured prompts
* safety + approvals
* visibility (logs + diffs)
* workspace management
* orchestration
