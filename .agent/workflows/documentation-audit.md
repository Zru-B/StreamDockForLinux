---
description: Systematic workflow for verifying documentation accuracy against source code
---

# Documentation Audit Workflow

This workflow ensures that the project's internal and external documentation remains a "Single Source of Truth" and does not drift from the actual implementation in `src/StreamDock`.

## Phase 0: User-Facing Documentation
- [ ] **Verify README.md**: Check that the main README accurately describes:
    - Installation prerequisites and steps.
    - Quick start guide.
    - Link to full documentation.
- [ ] **Verify Installation Docs** (`docs/installation.md`):
    - Cross-check Python version requirements against `pyproject.toml` or `requirements.txt`.
    - Verify `udev` rules installation steps.
    - Ensure system dependency lists (`hidapi`, `xdotool`, etc.) are current.
- [ ] **Verify Troubleshooting Guide** (`docs/troubleshooting.md`):
    - Check that common issues listed match current failure modes.
    - Verify proposed solutions are still valid.
- [ ] **Verify Device Setup** (`docs/device_setup.md`):
    - Ensure hardware setup instructions match current transport implementation.

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

### 4. Verify Configuration Documentation
- [ ] Compare `docs/configuration.md` against `src/StreamDock/config_loader.py`.
- [ ] Verify all configuration options documented in `docs/configuration.md` match the schema/defaults in the code.
- [ ] Check default `config.yml` against documented options.
- [ ] Ensure examples in documentation use valid configuration syntax.

### 5. Verify Actions Reference
- [ ] Compare `docs/actions_reference.md` against `src/StreamDock/actions.py`.
- [ ] Verify all documented actions exist in the actions registry.
- [ ] Check that action parameters, types, and descriptions match the implementation.
- [ ] Ensure no new actions have been added to code without documentation.

### 6. Code & Docstring Alignment
- [ ] Pick 3 core modules (e.g., `DeviceManager.py`, `actions.py`, `HIDTransport.py`).
- [ ] Verify that their Google-style docstrings accurately describe the current behavior/parameters.

## Phase 3: Pro-active Cleanup
- [ ] **Update**: Correct any outdated information found in Phase 2.
- [ ] **Remove**: Delete stale, irrelevant, or misleading data.
- [ ] **Add**: Include missing information or examples for newly added features.

## Phase 4: Final Deduplication & Conflict Resolution
- [ ] **Read EVERYTHING again**: Review all documentation files in one pass.
- [ ] **Eliminate Duplication**: If information is repeated across multiple files (and isn't a necessary summary), move it to the most suitable document type.
    - Example: If both README and installation.md have full install steps, keep detailed steps only in installation.md and link from README.
- [ ] **Resolve Conflicts**: Apply the following conflict resolution rules:
    - **Rule 1**: If `Documentation A` and `Documentation B` conflict on the same topic, the source code is the single source of truth.
    - **Rule 2**: Update BOTH conflicting documents to reflect the code's behavior.
    - **Rule 3**: If the code is wrong (bug), file an issue or fix the code, then update docs.
    - **Rule 4**: Document the date of audit in a comment or metadata if needed for future reference.
- [ ] **Link Verification**: Check all internal file links (e.g., `[text](file:///path)` or relative links) are valid.
    - Look for broken references to moved/renamed/deleted files.
    - Use `grep -r "](file://" docs/` or `grep -r "](.*/" docs/` to find links.
- [ ] **Schema Consistency**: Ensure consistent formatting across all markdown files:
    - Heading hierarchy (single H1 per file).
    - Code block language tags.
    - Alert box usage (GitHub-style `> [!NOTE]`, etc.).

---

> [!TIP]
> Use `grep_search` and `codebase_investigator` heavily during Phase 2 to ensure you don't miss hidden side-effects or renamed methods.
