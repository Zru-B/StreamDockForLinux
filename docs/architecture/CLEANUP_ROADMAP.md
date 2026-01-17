# Project Cleanup & Optimization Roadmap

This document lists detected inconsistencies and "low-hanging fruit" improvements for the StreamDockForLinux project.

---

## Low-Hanging Fruits (Quick Fixes)

### 1. Robust Image Cleanup
**Current**: `CHANGE_KEY_TEXT` uses a `threading.Thread` with `time.sleep(0.5)` to delete temp images.
**Improvement**: Use a proper temp directory (`tempfile.mkdtemp`) that is cleared on application shutdown, or store images in memory if a buffer-based `set_key_image` is added.

### 2. Mock Transport "CLI Virtual Deck"
**Current**: `MockTransport` only logs events.
**Improvement**: Implement a simple table/grid output in logs that shows the "current state" of the 15 keys whenever a layout changes.

### 3. Log Level Optimization
**Current**: Probing for tools (e.g., checking for `qdbus6`) can generate noise in standard logs.
**Improvement**: Ensure all "probing" and "attempting" logs are strictly `DEBUG` level, while `INFO` only shows actual successful transitions.

### 4. Simplified DBus Media Shortcuts
**Current**: Predefined shortcuts in `actions.py` are hardcoded for Spotify.
**Improvement**: Add a `media_player` setting in `config.yml` to allow the user to define their primary player (e.g., `vlc`, `rhythmbox`) instead of hardcoding Spotify strings.
