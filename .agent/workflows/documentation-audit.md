---
description: Systematic workflow for verifying documentation accuracy against source code
---

# Documentation Audit Workflow

This workflow ensures that the project's internal and external documentation remains a "Single Source of Truth" and does not drift from the actual implementation in `src/StreamDock`.

## Phase 1: Preparation
- [ ] **Check Audit Recency**: Look at the last modified date of this workflow or the `AGENT_KNOWLEDGE_BASE.md`. If it was more than 30 days ago, a full audit is required.
- [ ] **Define Scope**: The audit covers all `.md` files in `docs/` and `.agent/`, specifically comparing them against `src/StreamDock/`.

## Phase 2: Execution

### 1. Verify Agent Knowledge Base
- [ ] Compare `docs/architecture/AGENT_KNOWLEDGE_BASE.md` against current source code.
- [ ] **Check "Implementation Hints"**: Are the paths, method names, and logic still accurate?
- [ ] **Check "Known Limitations"**: Have any of these been resolved?
- [ ] **Check "Technical Debt"**: Add any new debt discovered during recent development.

### 2. Verify ADR Consistency
- [ ] Read all files in `docs/architecture/adr/`.
- [ ] Verify that the decisions documented are still the ones implemented in the code.
- [ ] If a decision has changed without a new ADR, create a "Superceding" ADR.

### 3. Verify Dependency Maps
- [ ] Review Mermaid diagrams in `docs/architecture/DEPENDENCY_MAP.md`.
- [ ] Run `grep -r "import"` to verify that class relationships and data flows haven't structurally changed.

### 4. Code & Docstring Alignment
- [ ] Pick 3 core modules (e.g., `DeviceManager.py`, `actions.py`, `HIDTransport.py`).
- [ ] Verify that their Google-style docstrings accurately describe the current behavior/parameters.

## Phase 3: Pro-active Cleanup
- [ ] **Update**: Correct any outdated information found in Phase 2.
- [ ] **Remove**: Delete stale, irrelevant, or misleading data.
- [ ] **Add**: Include missing information or examples for newly added features.

## Phase 4: Final Deduplication & Conflict Resolution
- [ ] **Read EVERYTHING again**: Review all documentation files in one pass.
- [ ] **Eliminate Duplication**: If information is repeated across multiple files (and isn't a necessary summary), move it to the most suitable document type.
- [ ] **Resolve Conflicts**: If two documents disagree, the source code is the truth. Update both documents to reflect the code.
- [ ] **Final Verification**: Ensure all links (file URLs) are valid.

---

> [!TIP]
> Use `grep_search` and `codebase_investigator` heavily during Phase 2 to ensure you don't miss hidden side-effects or renamed methods.
