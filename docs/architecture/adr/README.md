# Architecture Decision Records (ADR)

This directory contains records of significant architectural decisions made during the development of the StreamDockForLinux project.

## Purpose
ADRs provide context and rationale for design choices, ensuring that future maintainers (and AI agents) understand the constraints and reasons behind the current implementation.

## Format
Each ADR is a markdown file named `NNN-short-descriptive-title.md` and should include:
- **Status**: Proposed, Accepted, Superceded, etc.
- **Context**: The problem or requirement driving the decision.
- **Decision**: The chosen solution.
- **Consequences**: The impact of this decision (trade-offs, risks, required actions).

## Current Records
- [ADR-001: Use of hidapi via ctypes](001-use-hidapi-ctypes.md)
- [ADR-002: Transport Protocol Signature](002-transport-protocol.md)
- [ADR-003: D-Bus for Session & Hardware State Monitoring](003-dbus-monitoring.md)
