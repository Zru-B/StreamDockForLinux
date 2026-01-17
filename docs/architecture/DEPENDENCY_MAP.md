# Dependency Context Map

This document visualizes the core architecture, data flow, and component relationships within the `src/StreamDock` project.

## 1. High-Level Component Architecture

```mermaid
graph TD
    Main[main.py] --> DM[DeviceManager]
    Main --> WM[WindowMonitor]
    Main --> LM[LockMonitor]
    
    DM --> Dev[Device]
    Dev --> Trans[HIDTransport]
    
    DM --> Actions[actions.py]
    Actions --> WU[WindowUtils]
    
    WM --> WU
    LM --> DM
    
    CL[ConfigLoader] --> DM
    CL --> Layout[Layout/Key Models]
```

## 2. Data Flow: Hardware Event to System Action

```mermaid
sequenceDiagram
    participant User
    participant Device
    participant DM as DeviceManager
    participant Actions
    participant System

    User->>Device: Press Button
    Device->>DM: HID Interrupt (Report 1)
    DM->>DM: Map Index to Action (Current Layout)
    DM->>Actions: execute_actions(list)
    Actions->>System: xdotool / dbus / subprocess
    System-->>User: Visual/Audio Feedback
```

## 3. Device Lifecycle & State Machine

```mermaid
stateDiagram-v2
    [*] --> Disconnected
    Disconnected --> Connected: Device Plugin / Init
    Connected --> Active: App Start / Start Thread
    Active --> Suspended: Screen Lock (Brightness 0)
    Suspended --> Active: Screen Unlock (Restored)
    Active --> Disconnected: Device Unplugged
    Suspended --> Disconnected: Device Unplugged
    Disconnected --> [*]: App Close
```

## 4. Logical Dependencies (Internal Scope)

| Component | Depends On | Responsibilities |
| :--- | :--- | :--- |
| `DeviceManager` | `Device`, `ConfigLoader`, `actions` | Thread management, key-to-action routing. |
| `Device` | `HIDTransport` | High-level brightness and image commands. |
| `WindowMonitor` | `WindowUtils` | Polling for focus changes, triggering layout swaps. |
| `LockMonitor` | `DeviceManager` | D-Bus signal listening, power saving. |
| `actions.py` | `WindowUtils` | Input emulation and system integration. |

---

> [!NOTE]
> These diagrams represent the `src/StreamDock` core logic. External tools like `Configer` are excluded from this map.
