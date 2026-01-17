# Documentation Improvement: Plan & Todo List

This document tracks the comprehensive effort to bring the StreamDockForLinux documentation and SDLC processes to professional standards.
It should be updated as we progress through the project.
The file is structured as a todo list, with each item marked as completed or not completed.

It must not be added to the git repository. Once all tasks are completed and verified, it will be deleted.

## 📋 Todo List

### 1. Architecture Decision Records (ADR)
- [x] Initialize `docs/architecture/adr/` README explaining the ADR format.
- [x] **ADR-001**: Use of `hidapi` via `ctypes` (Avoid `hidraw` and kernel driver conflicts).
- [x] **ADR-002**: Transport Protocol Signature (`CRT` / 513-byte packets).
- [x] **ADR-003**: D-Bus for Session & Hardware State Monitoring.
- [ ] **Workflow Update**: Add ADR checkboxes to `bug-fix.md`, `feature-development.md`, and `refactoring.md`.

### 2. Release & QA Playbook
- [x] Create `docs/QA_PLAYBOOK.md` with:
    - Stability tests (Long-run, USB re-connect).
    - Security audits (Command injection, config sanitization).
    - Performance benchmarks (Window detection latency).
    - UI/UX consistency across environments.

### 3. Dependency Context Map
- [ ] Create `docs/architecture/DEPENDENCY_MAP.md` containing Mermaid diagrams.
    - Class relationships.
    - Data flow (Hardware Interrupt -> Action Execution).
    - Component State Machine (Connected, Locked, Active).

### 4. Documentation Maintenance Evolution
- [ ] **Sync Workflows**: Add "Post-Verification Documentation Update" steps to all workflows.
- [x] **Audit Workflow**: Create `.agent/workflows/documentation-audit.md`.

### 5. Domain Glossary
- [ ] Future task: Scan codebase in a clean context to generate exhaustive glossary.

---

## 🎯 Accuracy Boosters (Implementation Hints)

| Item | Accuracy Tips | Bullet-Proofing Suggestions |
| :--- | :--- | :--- |
| **ADR** | Cross-reference with `src/StreamDock/transport/HIDTransport.py` for exact byte counts and protocol details. | Include "Consequences" section in each ADR (e.g., "Must unbind hid-generic if device is grabbed"). |
| **QA Playbook** | Include `udev` rule verification steps. A common failure point is permissions. | Add a "Chaos Monkey" section: What happens if `xdotool` is uninstalled mid-run? |
| **Dependency Map** | Use `grep -r "import"` to verify actual dependencies before drawing. | Link diagrams to source files (provide paths in captions). |
| **Audit Workflow** | Ensure the audit checks the `README.md` first, as it's the user's first port of call. | Add a "Conflict Resolution" step: If 2 docs disagree, the code is the source of truth, and both docs must be updated. |

---

## 🚀 Suggested Improvements to Plan

1.  **CI-Integrated Doc Checks**: Add a task to implement a GitHub Action or local script that checks for broken file links within `.md` files. This prevents "link rot".
2.  **Automation of QA Playbook**: Some "measurable" items like "Config sanitization" can be turned into a small Python script `tests/security_audit.py` that the playbook can reference.
3.  **Visual Documentation**: Include a section for "Standard Hardware Layout" images in the QA Playbook to ensure icons are rendered at the correct resolution (e.g., 288x288 JPEG).
4.  **Auto-Audit Hint**: While agents can't auto-execute, we can add a check in the `instructions.md` that says: *"If the last audit was more than 30 days ago, prioritize running the documentation-audit workflow."*
