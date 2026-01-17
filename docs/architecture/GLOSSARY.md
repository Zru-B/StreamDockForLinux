# Domain Glossary

This document defines the core terminology used across the `src/StreamDock` project to ensure consistency in naming conventions and mental models.

> [!NOTE]
> This is a placeholder framework. A full-codebase scan should be performed in a clean context to populate this glossary exhaustively.

## Core Concepts

| Term | Definition |
| :--- | :--- |
| **Action** | A system-level task triggered by a key press (e.g., launching an app, simulating a key combo). |
| **Brightness** | The LCD backlight level, generally ranging from 0 (off) to 100 (max). |
| **Canvas** | The internal representation of the 288x288 pixel area for a single key or background. |
| **Device** | The physical Stream Dock 293v3 hardware. |
| **Key** | A specific hardware button (0-14 on the 293v3 model) and its associated data (icon, label, action). |
| **Layout** | A collection of 15 key definitions and a background image that can be applied to the device simultaneously. |
| **Packet** | A 513-byte unit of communication sent to the hardware via the `CRT` protocol. |
| **Transport** | The low-level communication layer (HID) responsible for sending and receiving raw data. |

## Automation Terms

| Term | Definition |
| :--- | :--- |
| **D-Bus Signal** | An inter-process notification used to detect system state changes (e.g., screen lock). |
| **Layout Switch** | The process of replacing the entire device state based on a trigger (e.g., window focus). |
| **Pulse** | A periodic check or update (e.g., polling the active window). |
| **Window Focus** | The state where a specific application window is receiving user input. |

---

> [!TIP]
> Always cross-reference this glossary when naming new classes or variables to maintain project-wide consistency.
