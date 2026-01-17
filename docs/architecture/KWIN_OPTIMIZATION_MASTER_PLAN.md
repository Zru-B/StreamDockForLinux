# KWin Window Detection Optimization - Master Plan

**Document Version**: 1.0  
**Date**: 2026-01-02  
**Status**: PLANNING - Ready for Implementation  
**Current Coverage**: 75%  
**Current Performance**: ~280ms per detection

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Current State Analysis](#current-state-analysis)
3. [Performance Measurements](#performance-measurements)
4. [Proposed Solutions](#proposed-solutions)
5. [Method Registry Pattern](#method-registry-pattern)
6. [Detailed Implementation Plans](#detailed-implementation-plans)
7. [Testing Strategy](#testing-strategy)
8. [Risk Analysis](#risk-analysis)
9. [Implementation Roadmap](#implementation-roadmap)

---

## Executive Summary

### Problem Statement
Current KWin window detection using journal-based scripting averages **280ms per call**, with significant overhead from:
- Script loading/unloading per call (100-150ms)
- Journal synchronization wait (50-200ms)  
- Journal parsing (10-30ms)

### Objectives
1. Reduce detection latency to **< 20ms** (14x improvement)
2. Eliminate journal dependency
3. Improve code maintainability through method registry pattern
4. Maintain backward compatibility with fallback chain

### Proposed Solution
Implement three-tiered detection system:
1. **Direct DBus** (Priority 1): ~10ms, zero init overhead
2. **File-Based Init-Once** (Priority 2): ~12ms, one-time 60-120ms init
3. **Current Journal** (Priority 3): ~280ms, fallback for compatibility

### Expected Outcomes
- **28x faster** on modern KDE systems (Direct DBus)
- **23x faster** on older KDE systems (File-Based)
- **No performance regression** (fallback to current method)
- **Cleaner codebase** (method registry pattern eliminates duplication)

---

## Current State Analysis

### Code Structure

**File**: `src/StreamDock/window_monitor.py`

**Current Detection Flow**:
```python
def get_active_window_info(self) -> WindowInfo | None:
    # Method 0: Simulation
    if self.simulation_mode:
        return self._try_simulation()
    
    # Method 1: KWin Scripting (journal-based)
    window_info = self._try_kwin_scripting()
    if window_info:
        return window_info
    
    # Method 2: kdotool
    if WindowUtils.is_kdotool_available():
        window_info = WindowUtils.kdotool_get_active_window()
        if window_info:
            return window_info
    
    # Method 3: Plasma Task Manager
    window_info = self._try_plasma_taskmanager()
    if window_info:
        return window_info
    
    # Method 4: KWin Basic
    window_info = self._try_kwin_basic()
    if window_info:
        return window_info
    
    return None
```

### Issues with Current Approach

**1. Code Duplication** ❌
- Repetitive if-check-return pattern
- Hard to add new methods
- Difficult to test method priority

**2. No Initialization** ❌
- Script loaded/unloaded every call
- Can't amortize setup costs
- No cleanup on application exit

**3. kwin_basic Limitations** ❌
```python
# Current kwin_basic only gets TITLE
window_title = qdbus("org.kde.KWin", "/KWin", "activeWindow")
window_class = extract_app_from_title(window_title)  # GUESSING!
```
- No resourceClass retrieval
- Must guess class from title
- Unreliable for many applications

**4. Performance** ❌
- Every call: 165-430ms (typical: 280ms)
- No optimization for repeated calls
- Wasteful for 500ms poll interval

---

## Performance Measurements

### Current Implementation: Journal-Based Scripting

**With Timing Decorators** (implemented in Step 520):
```python
@_timed("KWin script preparation")
def _prepare_kwin_script(self): ...

@_timed("KWin script loading")
def _load_kwin_script(self, script_path, plugin_name): ...

@_timed("Journal parsing with retry")
def _parse_journal_for_kwin_script_res(self, marker, wait_times=[0.05, 0.05, 0.10]): ...
```

**Measured Performance** (per call):
```
Preparation:          10-20ms  (read template, inject marker, write temp file)
Script Loading:       50-100ms (DBus loadScript call)
Script Execution:     5-10ms   (DBus run call)
Journal Retry Wait:   50-200ms (adaptive: 50ms, 50ms, 100ms attempts)
Journal Parsing:      10-30ms  (journalctl + search 100 lines)
Script Cleanup:       50-100ms (DBus unloadScript + file delete)
────────────────────────────────────────
TOTAL PER CALL:      165-430ms (typical: ~280ms)
```

**Adaptive Retry** (implemented in Step 547):
- Wait times: [50ms, 50ms, 100ms]
- Best case: Finds marker after 50ms (first attempt)
- Typical: Finds after 100ms (second attempt)
- Worst case: Finds after 200ms (third attempt) or fails

### Bottleneck Analysis

| Component | Time (ms) | % of Total | Optimizable? |
|-----------|-----------|------------|--------------|
| Script Load/Unload | 100-200 | 50% | ✅ **Init-Once** |
| Journal Wait | 50-200 | 30% | ✅ **Eliminate** |
| Preparation | 10-20 | 5% | ✅ **Init-Once** |
| Execution | 5-10 | 3% | ⚠️ Required |
| Journal Parse | 10-30 | 7% | ✅ **Eliminate** |
| Cleanup | 50-100 | 20% | ✅ **Defer** |

**Key Insight**: 85% of time is eliminable through init-once + journal elimination!

---

## Proposed Solutions

### Solution 1: Direct DBus Query ⭐ **RECOMMENDED**

**Concept**: Query KWin window objects directly via DBus without custom scripts.

#### Why It's Better Than kwin_basic

**Current kwin_basic**:
```python
# Only gets window title (NOT resourceClass!)
title = qdbus("org.kde.KWin", "/KWin", "activeWindow")
class = extract_app_from_title(title)  # Unreliable guessing!
```

**Direct DBus**:
```python
# Gets window ID first
window_id = qdbus("org.kde.KWin", "/KWin", "activeWindow")

# Then queries window object for BOTH properties
title = qdbus("org.kde.KWin", f"/Windows/{window_id}", "caption")
resource_class = qdbus("org.kde.KWin", f"/Windows/{window_id}", "resourceClass")
# ✅ Accurate! No guessing!
```

#### Implementation

```python
@_timed("KWin DBus Direct")
def _detect_kwin_dbus_direct(self) -> WindowInfo | None:
    """Direct DBus query - fastest method."""
    try:
        # Get active window ID
        result = subprocess.run(
            [self.qdbus_cmd, "org.kde.KWin", "/KWin", "activeWindow"],
            capture_output=True, text=True, timeout=1, check=False
        )
        
        if result.returncode != 0:
            return None
        
        window_id = result.stdout.strip()
        if not window_id:
            return None
        
        # Get window properties
        window_path = f"/Windows/{window_id}"
        
        # Parallel property fetch
        title_proc = subprocess.Popen(
            [self.qdbus_cmd, "org.kde.KWin", window_path, "caption"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        
        class_proc = subprocess.Popen(
            [self.qdbus_cmd, "org.kde.KWin", window_path, "resourceClass"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        
        title_out, _ = title_proc.communicate(timeout=1)
        class_out, _ = class_proc.communicate(timeout=1)
        
        if not title_out or not class_out:
            return None
        
        title = title_out.strip()
        resource_class = class_out.strip()
        window_class = WindowUtils.normalize_class_name(resource_class, title)
        
        return WindowInfo(
            title=title,
            class_=window_class,
            raw=f"{title}|{resource_class}",
            method="kwin_dbus_direct",
            window_id=window_id
        )
    except Exception as e:
        logger.debug(f"Direct DBus failed: {e}")
        return None
```

#### Performance

**Per Call**:
```
Get window ID:       3-6ms   (single DBus call)
Get properties:      4-8ms   (2 parallel DBus calls)
Normalization:       1-2ms   (Python string ops)
────────────────────────────────
TOTAL:              8-16ms   (typical: ~10ms)
```

**Speedup**: **28x faster** than current (280ms → 10ms)

#### Compatibility

**Requirements**:
- KDE Plasma 5.24+ (window objects on DBus)
- qdbus6 or qdbus command

**Availability Check**:
```python
def check_availability(self) -> bool:
    """Check if KWin DBus direct query is supported."""
    for cmd in ["qdbus6", "qdbus"]:
        if shutil.which(cmd):
            try:
                # Test if /Windows path exists
                result = subprocess.run(
                    [cmd, "org.kde.KWin", "/KWin"],
                    capture_output=True, timeout=0.5
                )
                if result.returncode == 0:
                    self.qdbus_cmd = cmd
                    return True
            except subprocess.TimeoutExpired:
                pass
    return False
```

#### Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| KWin version lacks API | Medium | High | Fallback to File-Based |
| Property names change | Low | Medium | Version detection |
| DBus timeout | Low | Low | 1s timeout, fallback |

---

### Solution 2: File-Based (Init-Once) ⭐ **FALLBACK**

**Concept**: Load persistent KWin script once that writes to temp file.

#### Architecture

**Initialization** (once at startup):
```
1. Cleanup leftover files from previous crash
2. Read kwin_detect_file.js template
3. Load script into KWin (keep loaded)
4. Store script_id for later use
```

**Per Detection Call**:
```
1. Execute loaded script (DBus run)      ~5-10ms
2. Script writes to /tmp/streamdock      ~1-3ms
3. Read file from Python                 ~2-3ms
────────────────────────────────────────
TOTAL:                                   ~8-15ms
```

**Cleanup** (once at shutdown):
```
1. Unload script from KWin
2. Delete temp file
```

#### Implementation

**KWin Script**: `src/StreamDock/scripts/kwin_detect_file.js`
```javascript
/**
 * StreamDock File-Based Window Detector
 * Writes active window info to /tmp/streamdock_window
 */

var OUTPUT_FILE = "/tmp/streamdock_window";

function detectWindow() {
    var active = workspace.activeWindow;
    var result = "None|None";
    
    if (active && active.caption && active.resourceClass) {
        // Escape pipes in caption
        var title = String(active.caption).split('|').join(' ');
        var cls = String(active.resourceClass);
        result = title + "|" + cls;
    }
    
    // Write to file using Qt API
    var file = new TextStream();
    if (file.open(OUTPUT_FILE, QIODevice.WriteOnly | QIODevice.Text)) {
        file.writeLine(result);
        file.close();
        return true;
    } else {
        console.error("StreamDock: Failed to write " + OUTPUT_FILE);
        return false;
    }
}

// Execute immediately
detectWindow();
```

**Python Detection Class**:
```python
class FileBasedDetection:
    """File-based detection with persistent script."""
    
    def __init__(self):
        self.script_id = None
        self.output_file = "/tmp/streamdock_window"
        self.qdbus_cmd = None
        self.script_path = None
    
    def initialize(self) -> bool:
        """Load script once at startup."""
        try:
            # Cleanup leftover file
            if os.path.exists(self.output_file):
                os.remove(self.output_file)
                logger.info(f"Cleaned up leftover file: {self.output_file}")
            
            # Find qdbus command
            for cmd in ["qdbus6", "qdbus"]:
                if shutil.which(cmd):
                    self.qdbus_cmd = cmd
                    break
            
            if not self.qdbus_cmd:
                logger.error("No qdbus command found")
                return False
            
            # Prepare script
            base_dir = os.path.dirname(os.path.abspath(__file__))
            self.script_path = os.path.join(base_dir, "scripts", "kwin_detect_file.js")
            
            if not os.path.exists(self.script_path):
                logger.error(f"Script not found: {self.script_path}")
                return False
            
            # Start KWin scripting
            subprocess.run(
                [self.qdbus_cmd, "org.kde.KWin", "/Scripting",
                 "org.kde.kwin.Scripting.start"],
                capture_output=True, timeout=2, check=False
            )
            
            # Unload any previous instance
            subprocess.run(
                [self.qdbus_cmd, "org.kde.KWin", "/Scripting",
                 "org.kde.kwin.Scripting.unloadScript", "streamdock_persistent"],
                capture_output=True, timeout=1, check=False
            )
            
            # Load script
            result = subprocess.run(
                [self.qdbus_cmd, "org.kde.KWin", "/Scripting",
                 "org.kde.kwin.Scripting.loadScript",
                 self.script_path, "streamdock_persistent"],
                capture_output=True, text=True, timeout=2, check=False
            )
            
            if result.returncode != 0:
                logger.error(f"Failed to load script: {result.stderr}")
                return False
            
            script_id_str = result.stdout.strip()
            if not script_id_str.lstrip('-').isdigit():
                logger.error(f"Invalid script ID: {script_id_str}")
                return False
            
            self.script_id = int(script_id_str)
            
            if self.script_id < 0:
                logger.error(f"KWin returned negative script ID: {self.script_id}")
                return False
            
            logger.info(f"✅ File-based detection initialized (script_id={self.script_id})")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize file-based detection: {e}")
            return False
    
    @_timed("File-based detection")
    def detect(self) -> WindowInfo | None:
        """Execute loaded script and read result."""
        if self.script_id is None:
            return None
        
        try:
            # Remove old file if exists
            if os.path.exists(self.output_file):
                os.remove(self.output_file)
            
            # Execute script
            script_obj = f"/Scripting/Script{self.script_id}"
            result = subprocess.run(
                [self.qdbus_cmd, "org.kde.KWin", script_obj,
                 "org.kde.kwin.Script.run"],
                capture_output=True, timeout=1, check=False
            )
            
            if result.returncode != 0:
                logger.debug(f"Script execution failed: {result.stderr}")
                return None
            
            # Brief wait for file write (usually instant)
            time.sleep(0.003)  # 3ms
            
            # Read result
            if not os.path.exists(self.output_file):
                logger.debug("Output file not created")
                return None
            
            with open(self.output_file, 'r') as f:
                data = f.read().strip()
            
            if not data or '|' not in data:
                logger.debug(f"Invalid data: {data}")
                return None
            
            title, resource_class = data.split('|', 1)
            
            if title == "None" and resource_class == "None":
                return None
            
            window_class = WindowUtils.normalize_class_name(resource_class, title)
            
            return WindowInfo(
                title=title,
                class_=window_class,
                raw=data,
                method="kwin_file_based"
            )
            
        except Exception as e:
            logger.debug(f"File-based detection failed: {e}")
            return None
    
    def cleanup(self):
        """Unload script and cleanup file."""
        if self.script_id is not None:
            try:
                subprocess.run(
                    [self.qdbus_cmd, "org.kde.KWin", "/Scripting",
                     "org.kde.kwin.Scripting.unloadScript",
                     "streamdock_persistent"],
                    capture_output=True, timeout=1, check=False
                )
                logger.info("✅ Unloaded persistent script")
            except Exception as e:
                logger.debug(f"Script unload failed: {e}")
        
        # Cleanup file
        if os.path.exists(self.output_file):
            try:
                os.remove(self.output_file)
            except Exception as e:
                logger.debug(f"File cleanup failed: {e}")
```

#### Performance

**Initialization** (once):
```
File check/cleanup:    1-2ms
Find qdbus:           1-2ms
Read script:          5-10ms
Load script (DBus):   50-100ms
────────────────────────────────
TOTAL INIT:          60-120ms (one-time cost)
```

**Per Call** (steady state):
```
Remove old file:      0-1ms
Execute script:       5-10ms
File write (in KWin): 1-3ms
Sleep:               3ms
Read file:           2-3ms
Parse:               1ms
────────────────────────────────
TOTAL:               12-18ms (typical: ~12ms)
```

**Speedup**: **23x faster** than current (280ms → 12ms)

#### Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| File permissions | Low | Medium | Use /tmp |
| QFile API changes | Very Low | Low | Test on target KDE version |
| Script crashes | Low | Medium | Auto-reload on failure |
| Concurrent access | Very Low | Low | Unique filename |

---

### Solution 3: DBus Property (Documentation Only)

**Concept**: Register DBus service, KWin script sets property, Python reads property.

**Why Not Recommended**:
- Requires `pydbus` dependency
- Complex service lifecycle management
- Only 5ms faster than File-Based (~7ms vs ~12ms)
- Higher implementation complexity (2 days vs 5 hours)

**Implementation effort**: Not justified for marginal performance gain.

**Full implementation details**: See `kwin_optimization_plan.md` Phase 3

---

## Method Registry Pattern

### Problem with Current Code

```python
def get_active_window_info(self):
    # Repetitive pattern:
    if self.simulation_mode:
        return self._try_simulation()
    
    window_info = self._try_kwin_scripting()
    if window_info:
        return window_info
    
    if WindowUtils.is_kdotool_available():
        window_info = WindowUtils.kdotool_get_active_window()
        if window_info:
            return window_info
    
    # ... repeated 3 more times
```

**Issues**:
- ❌ Code duplication (if-check-return pattern)
- ❌ Hard to add new methods
- ❌ No centralized initialization/cleanup
- ❌ Difficult to test priority ordering
- ❌ No visibility into why method was chosen

### Proposed Registry Architecture

#### Base Interface

```python
from abc import ABC, abstractmethod
from typing import Optional

class DetectionMethod(ABC):
    """Base class for window detection methods."""
    
    def __init__(self, name: str, priority: int):
        """
        Initialize detection method.
        
        Args:
            name: Unique identifier for this method
            priority: Execution priority (passed from WindowMonitor)
                     Lower number = higher priority (0 is highest)
        """
        self.name = name
        self.priority = priority
        self.available = False
        self.initialized = False
    
    @abstractmethod
    def check_availability(self) -> bool:
        """
        Check if this detection method is available on the system.
        
        Should be lightweight (< 100ms) as it's called at startup.
        Sets self.available = True if successful.
        
        Returns:
            bool: True if method is available, False otherwise
        """
        pass
    
    def initialize(self) -> bool:
        """
        Initialize method resources (called once at startup).
        
        Override this for methods that need one-time setup.
        Default implementation does nothing (for init-free methods).
        
        Returns:
            bool: True if initialization succeeded, False otherwise
        """
        self.initialized = True
        return True
    
    @abstractmethod
    def detect(self) -> Optional[WindowInfo]:
        """
        Attempt to detect the active window.
        
        Returns:
            WindowInfo if successful, None if detection failed
        """
        pass
    
    def cleanup(self):
        """
        Cleanup method resources (called at shutdown).
        
        Override this for methods that need cleanup.
        Default implementation does nothing.
        """
        pass
    
    def __repr__(self):
        return f"<{self.__class__.__name__} priority={self.priority} available={self.available}>"
```

#### Concrete Implementations

**1. Direct DBus Method**:
```python
class DirectDbusMethod(DetectionMethod):
    """Fast direct DBus query (Plasma 5.24+)."""
    
    def __init__(self, priority: int):
        """
        Args:
            priority: Execution priority (set by WindowMonitor)
        """
        super().__init__("kwin_dbus_direct", priority)
        self.qdbus_cmd = None
    
    def check_availability(self) -> bool:
        """Check if KWin DBus is accessible."""
        for cmd in ["qdbus6", "qdbus"]:
            if shutil.which(cmd):
                try:
                    result = subprocess.run(
                        [cmd, "org.kde.KWin", "/KWin"],
                        capture_output=True, timeout=0.5
                    )
                    if result.returncode == 0:
                        self.qdbus_cmd = cmd
                        self.available = True
                        logger.info(f"✅ Direct DBus available ({cmd})")
                        return True
                except subprocess.TimeoutExpired:
                    pass
        
        logger.debug("❌ Direct DBus not available")
        self.available = False
        return False
    
    @_timed("Direct DBus detection")
    def detect(self) -> Optional[WindowInfo]:
        # Implementation from Solution 1
        ...
```

**2. File-Based Method**:
```python
class FileBasedMethod(DetectionMethod):
    """File-based with persistent script."""
    
    def __init__(self, priority: int):
        """
        Args:
            priority: Execution priority (set by WindowMonitor)
        """
        super().__init__("kwin_file_based", priority)
        self.script_id = None
        self.output_file = "/tmp/streamdock_window"
        self.qdbus_cmd = None
    
    def check_availability(self) -> bool:
        """Check if KWin scripting is available."""
        # Implementation from Solution 2
        ...
    
    def initialize(self) -> bool:
        """Load persistent script."""
        # Implementation from Solution 2
        ...
    
    @_timed("File-based detection")
    def detect(self) -> Optional[WindowInfo]:
        # Implementation from Solution 2
        ...
    
    def cleanup(self):
        """Unload script and remove file."""
        # Implementation from Solution 2
        ...
```

**3. Legacy Method Wrappers**:
```python
class JournalScriptingMethod(DetectionMethod):
    """Current journal-based method (fallback)."""
    
    def __init__(self, monitor, priority: int):
        """
        Args:
            monitor: WindowMonitor instance
            priority: Execution priority (set by WindowMonitor)
        """
        super().__init__("kwin_journal_scripting", priority)
        self.monitor = monitor
        self.available = True  # Always available
    
    def check_availability(self) -> bool:
        self.available = True
        return True
    
    @_timed("Journal scripting detection")
    def detect(self) -> Optional[WindowInfo]:
        return self.monitor._try_kwin_scripting()


class KdotoolMethod(DetectionMethod):
    """kdotool legacy method."""
    
    def __init__(self, priority: int):
        """
        Args:
            priority: Execution priority (set by WindowMonitor)
        """
        super().__init__("kdotool", priority)
    
    def check_availability(self) -> bool:
        self.available = WindowUtils.is_kdotool_available()
        return self.available
    
    def detect(self) -> Optional[WindowInfo]:
        return WindowUtils.kdotool_get_active_window()
```

#### WindowMonitor Integration

**✨ Key Improvement: Centralized Priority Management**

```python
class WindowMonitor:
    """Monitor active window with pluggable detection methods."""
    
    def __init__(self, poll_interval=0.5, simulation_mode=False):
        self.poll_interval = poll_interval
        self.simulation_mode = simulation_mode
        self.current_window_id = None
        self.current_window_detection_method = None
        self.window_rules = []
        self.running = False
        
        # Register all detection methods
        self.detection_methods: list[DetectionMethod] = []
        self._register_detection_methods()
        
        # Initialize methods
        self._initialize_detection_methods()
    
    def _register_detection_methods(self):
        """
        Register all available detection methods.
        
        ✨ Priority is defined HERE in one central location!
        Lower priority number = tried first.
        """
        methods = [
            DirectDbusMethod(priority=1),           # Fastest - try first
            FileBasedMethod(priority=2),            # Fast fallback
            JournalScriptingMethod(self, priority=3), # Slow but reliable
            KdotoolMethod(priority=4),              # Legacy
            PlasmaTaskManagerMethod(priority=5),    # Legacy
        ]
        
        # Add simulation mode first if enabled
        if self.simulation_mode:
            methods.insert(0, SimulationMethod(self, priority=0))
        
        self.detection_methods = methods
        logger.info(f"Registered {len(methods)} detection methods")
        logger.info(f"Priority order: {[(m.name, m.priority) for m in methods]}")

    
    def _initialize_detection_methods(self):
        """Check availability and initialize all methods."""
        available_count = 0
        initialized_count = 0
        
        for method in self.detection_methods:
            # Check availability
            if method.check_availability():
                available_count += 1
                logger.info(f"  ✅ {method.name} available")
                
                # Initialize if needed
                if method.initialize():
                    initialized_count += 1
                    logger.info(f"  ✅ {method.name} initialized")
                else:
                    logger.warning(f"  ⚠️  {method.name} init failed")
                    method.available = False
            else:
                logger.debug(f"  ❌ {method.name} not available")
        
        # Sort by priority (lower number = higher priority)
        self.detection_methods.sort(key=lambda m: m.priority)
        
        logger.info(f"Detection: {available_count} available, {initialized_count} initialized")
        logger.info(f"Priority order: {[m.name for m in self.detection_methods if m.available]}")
    
    def get_active_window_info(self) -> Optional[WindowInfo]:
        """
        Get active window info using registered detection methods.
        
        Tries methods in priority order until one succeeds.
        
        Returns:
            WindowInfo if any method succeeded, None otherwise
        """
        for method in self.detection_methods:
            if not method.available:
                continue
            
            try:
                result = method.detect()
                if result is not None:
                    self.current_window_detection_method = method.name
                    logger.debug(f"✅ Detected using {method.name}")
                    return result
            except Exception as e:
                logger.warning(f"❌ {method.name} failed: {e}")
                continue
        
        logger.debug("❌ All detection methods failed")
        self.current_window_detection_method = None
        return None
    
    def stop(self):
        """Stop monitoring and cleanup all methods."""
        self.running = False
        
        # Cleanup all methods
        for method in self.detection_methods:
            if method.initialized:
                try:
                    method.cleanup()
                    logger.info(f"✅ Cleaned up {method.name}")
                except Exception as e:
                    logger.warning(f"⚠️  Cleanup failed for {method.name}: {e}")
```

### Benefits of Registry Pattern

**1. DRY Principle** ✅
- No repetitive if-check-return code
- Single detection loop

**2. Easy Extensibility** ✅
```python
# Adding new method is trivial:
class NewMethod(DetectionMethod):
    def __init__(self):
        super().__init__("new_method", priority=1)
    
    def check_availability(self): ...
    def detect(self): ...

# Register it:
methods.insert(0, NewMethod())
```

**3. Centralized Lifecycle** ✅
- Initialization in one place
- Cleanup automatically handled
- Clear startup/shutdown sequence

**4. Better Testing** ✅
```python
def test_method_priority():
    monitor = WindowMonitor()
    
    # Verify priority order
    available = [m for m in monitor.detection_methods if m.available]
    priorities = [m.priority for m in available]
    
    assert priorities == sorted(priorities)

def test_fallback_chain():
    monitor = WindowMonitor()
    
    # Disable fast methods
    for method in monitor.detection_methods:
        if method.name in ["kwin_dbus_direct", "kwin_file_based"]:
            method.available = False
    
    # Should fall back to journal
    result = monitor.get_active_window_info()
    assert result.method == "kwin_journal_scripting"
```

**5. Runtime Visibility** ✅
```python
# Log what method was used
logger.info(f"Used {monitor.current_window_detection_method}")

# Query method status
for method in monitor.detection_methods:
    print(f"{method.name}: available={method.available}, priority={method.priority}")
```

---

## Detailed Implementation Plans

### Phase 0: Method Registry Refactoring

**Goal**: Eliminate code duplication, enable easy method registration

**Files to Create**:
- `src/StreamDock/detection/base.py` - Base classes
- `src/StreamDock/detection/direct_dbus.py` - Direct DBus implementation
- `src/StreamDock/detection/file_based.py` - File-based implementation
- `src/StreamDock/detection/legacy.py` - Wrapper for existing methods
- `src/StreamDock/detection/__init__.py` - Exports

**Files to Modify**:
- `src/StreamDock/window_monitor.py` - Use registry pattern

**Steps**:

1. **Create detection module** (30 min)
```bash
mkdir -p src/StreamDock/detection
touch src/StreamDock/detection/__init__.py
```

2. **Implement base class** (1 hour)
   - `detection/base.py` with `DetectionMethod` ABC
   - Include all abstract methods
   - Add timing decorator support

3. **Create legacy wrappers** (1 hour)
   - `detection/legacy.py`
   - Wrap existing `_try_kwin_scripting()`, `kdotool`, etc.
   - Maintain exact same behavior

4. **Refactor WindowMonitor** (2 hours)
   - Replace detection logic with registry
   - Add `_register_detection_methods()`
   - Add `_initialize_detection_methods()`
   - Update `get_active_window_info()`

5. **Test refactoring** (1 hour)
   - Run all existing tests
   - Verify no regressions
   - Add registry-specific tests

**Success Criteria**:
- ✅ All existing tests pass
- ✅ No performance regression
- ✅ Code is DRY
- ✅ Easy to add new methods

**Estimated Time**: 6 hours

---

### Phase 1: Direct DBus Implementation

**Goal**: Add fastest detection method

**Prerequisites**: Phase 0 complete

**Steps**:

1. **Create DirectDbusMethod class** (1 hour)
   - File: `detection/direct_dbus.py`
   - Implement `check_availability()`
   - Implement `detect()` with parallel property fetch

2. **Test Direct DBus** (1 hour)
   ```python
   def test_direct_dbus_availability():
       method = DirectDbusMethod()
       # Should find qdbus6 or qdbus
       ...
   
   def test_direct_dbus_detection():
       method = DirectDbusMethod()
       # Mock subprocess calls
       ...
   ```

3. **Register method** (15 min)
   - Add to `_register_detection_methods()`
   - Set priority=1

4. **Integration test** (30 min)
   - Test on real KDE system
   - Verify 10ms performance
   - Test fallback if unavailable

5. **Documentation** (15 min)
   - Update README
   - Add performance notes

**Success Criteria**:
- ✅ Method detects on KDE 5.24+
- ✅ < 20ms detection time
- ✅ Graceful fallback
- ✅ Tests passing

**Estimated Time**: 3 hours

---

### Phase 2: File-Based Implementation

**Goal**: Add init-once fallback method

**Prerequisites**: Phase 0 complete

**Steps**:

1. **Create KWin script** (1 hour)
   - File: `scripts/kwin_detect_file.js`
   - Implement file writing with QFile API
   - Add error handling
   - Test script manually:
     ```bash
     qdbus6 org.kde.KWin /Scripting org.kde.kwin.Scripting.loadScript \
       $(pwd)/src/StreamDock/scripts/kwin_detect_file.js test_script
     
     qdbus6 org.kde.KWin /Scripting/Script<ID> org.kde.kwin.Script.run
     
     cat /tmp/streamdock_window
     ```

2. **Create FileBasedMethod class** (2 hours)
   - File: `detection/file_based.py`
   - Implement `check_availability()`
   - Implement `initialize()` - load script once
   - Implement `detect()` - execute and read file
   - Implement `cleanup()` - unload script

3. **Test File-Based** (1 hour)
   ```python
   def test_file_based_init():
       method = FileBasedMethod()
       assert method.initialize()
       assert method.script_id is not None
   
   def test_file_based_detection():
       method = FileBasedMethod()
       method.initialize()
       result = method.detect()
       assert result is not None
   
   def test_file_based_cleanup():
       method = FileBasedMethod()
       method.initialize()
       method.cleanup()
       assert not os.path.exists(method.output_file)
   ```

4. **Register method** (15 min)
   - Add to `_register_detection_methods()`
   - Set priority=2

5. **Integration test** (30 min)
   - Test initialization at startup
   - Verify 12ms performance
   - Test cleanup at shutdown
   - Test crash recovery (leftover files)

6. **Documentation** (15 min)

**Success Criteria**:
- ✅ Script loads successfully
- ✅ < 20ms detection time
- ✅ Proper cleanup
- ✅ Crash recovery works

**Estimated Time**: 5 hours

---

## Testing Strategy

### Unit Tests

**File**: `tests/detection/test_direct_dbus.py`
```python
import pytest
from unittest.mock import MagicMock, patch
from StreamDock.detection.direct_dbus import DirectDbusMethod

class TestDirectDbusMethod:
    def test_availability_check_qdbus6(self):
        """Test availability with qdbus6."""
        method = DirectDbusMethod()
        
        with patch('shutil.which') as mock_which:
            mock_which.return_value = "/usr/bin/qdbus6"
            
            with patch('subprocess.run') as mock_run:
                mock_run.return_value = MagicMock(returncode=0)
                
                assert method.check_availability()
                assert method.qdbus_cmd == "qdbus6"
                assert method.available
    
    def test_detection_success(self):
        """Test successful window detection."""
        method = DirectDbusMethod()
        method.qdbus_cmd = "qdbus6"
        method.available = True
        
        with patch('subprocess.run') as mock_run:
            # Mock window ID call
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="123\n"
            )
            
            with patch('subprocess.Popen') as mock_popen:
                # Mock property calls
                title_proc = MagicMock()
                title_proc.communicate.return_value = ("Firefox\n", "")
                
                class_proc = MagicMock()
                class_proc.communicate.return_value = ("firefox\n", "")
                
                mock_popen.side_effect = [title_proc, class_proc]
                
                result = method.detect()
                
                assert result is not None
                assert result.title == "Firefox"
                assert result.class_ == "firefox"
                assert result.method == "kwin_dbus_direct"
    
    def test_detection_no_window(self):
        """Test detection when no window is active."""
        method = DirectDbusMethod()
        method.qdbus_cmd = "qdbus6"
        
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="")
            
            result = method.detect()
            assert result is None
```

**File**: `tests/detection/test_file_based.py`
```python
class TestFileBasedMethod:
    def test_initialization(self):
        """Test script loading."""
        # Mock subprocess, file operations
        ...
    
    def test_detection(self):
        """Test file-based detection."""
        # Create method, mock script execution, verify file read
        ...
    
    def test_cleanup(self):
        """Test cleanup."""
        # Verify script unloaded, file deleted
        ...
```

### Integration Tests

**File**: `tests/test_window_monitor_integration.py`
```python
class TestDetectionIntegration:
    def test_method_priority_order(self):
        """Verify methods are tried in correct order."""
        monitor = WindowMonitor()
        
        methods = [m for m in monitor.detection_methods if m.available]
        priorities = [m.priority for m in methods]
        
        # Verify sorted by priority
        assert priorities == sorted(priorities)
    
    def test_fallback_chain(self):
        """Test fallback when fast methods fail."""
        monitor = WindowMonitor()
        
        # Disable Direct DBus and File-Based
        for method in monitor.detection_methods:
            if method.name in ["kwin_dbus_direct", "kwin_file_based"]:
                method.available = False
        
        result = monitor.get_active_window_info()
        
        # Should use journal method
        assert monitor.current_window_detection_method == "kwin_journal_scripting"
    
    def test_cleanup_all_methods(self):
        """Test that stop() cleans up all methods."""
        monitor = WindowMonitor()
        
        # Initialize
        monitor._initialize_detection_methods()
        
        # Stop
        monitor.stop()
        
        # Verify cleanup called on all
        # (check log messages or file existence)
```

### Performance Tests

**File**: `tests/performance/test_detection_speed.py`
```python
import time
import pytest

@pytest.mark.performance
class TestDetectionPerformance:
    def test_direct_dbus_speed(self):
        """Verify Direct DBus < 20ms."""
        method = DirectDbusMethod()
        if not method.check_availability():
            pytest.skip("Direct DBus not available")
        
        timings = []
        for _ in range(10):
            start = time.time()
            result = method.detect()
            elapsed = (time.time() - start) * 1000
            timings.append(elapsed)
        
        avg_time = sum(timings) / len(timings)
        assert avg_time < 20, f"Too slow: {avg_time:.1f}ms"
    
    def test_file_based_speed(self):
        """Verify File-Based < 20ms."""
        method = FileBasedMethod()
        if not method.check_availability():
            pytest.skip("File-Based not available")
        
        method.initialize()
        
        timings = []
        for _ in range(10):
            start = time.time()
            result = method.detect()
            elapsed = (time.time() - start) * 1000
            timings.append(elapsed)
        
        method.cleanup()
        
        avg_time = sum(timings) / len(timings)
        assert avg_time < 20, f"Too slow: {avg_time:.1f}ms"
```

---

## Risk Analysis

### Technical Risks

| Risk | Probability | Impact | Mitigation | Owner |
|------|-------------|--------|------------|-------|
| **KWin API incompatibility** | Medium | High | Fallback chain, version detection | Phase 1 |
| **File I/O race conditions** | Low | Medium | Unique filenames, proper locking | Phase 2 |
| **Script crashes** | Low | Medium | Error handling, auto-reload | Phase 2 |
| **Performance regression** | Very Low | High | Benchmark tests, fallback | All |
| **Memory leaks** | Very Low | Medium | Proper cleanup, testing | Phase 2 |

### Project Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| **Scope creep** | Medium | Medium | Stick to 3 phases, defer DBus Property |
| **Testing gaps** | Low | High | Comprehensive test plan, coverage metrics |
| **Breaking changes** | Low | High | Backward compatibility, fallbacks |
| **Time overrun** | Medium | Low | Phased approach, MVP focus |

---

## Implementation Roadmap

### Timeline

| Phase | Task | Duration | Dependencies | Risk |
|-------|------|----------|--------------|------|
| **Phase 0** | Method Registry Refactoring | 6 hours | None | Low |
| | - Create detection module | 30 min | | |
| | - Implement base class | 1 hour | | |
| | - Create legacy wrappers | 1 hour | | |
| | - Refactor WindowMonitor | 2 hours | | |
| | - Testing | 1.5 hours | | |
| **Phase 1** | Direct DBus Implementation | 3 hours | Phase 0 | Medium |
| | - Create method class | 1 hour | | |
| | - Unit tests | 1 hour | | |
| | - Integration | 1 hour | | |
| **Phase 2** | File-Based Implementation | 5 hours | Phase 0 | Low |
| | - Create KWin script | 1 hour | | |
| | - Create method class | 2 hours | | |
| | - Tests | 1 hour | | |
| | - Integration | 1 hour | | |
| **Total** | | **14 hours** | | |

### Milestones

**M1: Registry Refactoring Complete** (After Phase 0)
- ✅ No code duplication
- ✅ Easy to add methods
- ✅ All existing tests pass
- ✅ No performance regression

**M2: Direct DBus Available** (After Phase 1)
- ✅ < 20ms detection on supported systems
- ✅ Graceful fallback
- ✅ Tests passing

**M3: File-Based Available** (After Phase 2)
- ✅ < 20ms detection on most systems
- ✅ Proper initialization/cleanup
- ✅ All tests passing

### Success Metrics

**Performance**:
- 95th percentile detection time < 20ms
- Average detection time < 15ms
- Zero performance regression for fallback methods

**Quality**:
- Test coverage ≥ 80%
- Zero critical bugs
- All integration tests pass

**Maintainability**:
- Lines of code reduced by 30%
- Cyclomatic complexity reduced
- Easy to add new methods (< 100 LOC)

---

## Appendix

### A. Current Code Analysis

**File**: `src/StreamDock/window_monitor.py`  
**Line Count**: 618 lines  
**Current Methods**: 5 (simulation, kwin_scripting, kdotool, plasma, kwin_basic)  
**Duplication**: ~40 lines (if-check-return pattern × 5)

### B. Expected Code Changes

**Lines Added**: ~800
- `detection/base.py`: ~150
- `detection/direct_dbus.py`: ~120
- `detection/file_based.py`: ~200
- `detection/legacy.py`: ~100
- `detection/__init__.py`: ~20
- `scripts/kwin_detect_file.js`: ~30
- Tests: ~180

**Lines Removed**: ~200
- Deduplicated detection code in `window_monitor.py`

**Net Change**: +600 lines (but much better organized)

### C. Dependencies

**New Dependencies**: None!
- Uses existing `subprocess`, `os`, `shutil`
- QFile already available in KWin

**Optional Dependencies**:
- `pydbus` (only if implementing DBus Property - skipped)

### D. Backward Compatibility

**Guaranteed**:
- ✅ Existing methods still available as fallbacks
- ✅ No API changes to `WindowMonitor`
- ✅ Same `WindowInfo` return type
- ✅ Simulation mode unchanged

**Migration Path**:
- Drop-in replacement
- No config changes needed
- Automatic method selection

---

## Conclusion

This plan provides:

✅ **Clear problem definition** (280ms → 10-15ms)  
✅ **Detailed solutions** (3 approaches fully documented)  
✅ **Method registry pattern** (eliminates duplication)  
✅ **Step-by-step implementation** (14 hours, 3 phases)  
✅ **Comprehensive testing** (unit, integration, performance)  
✅ **Risk mitigation** (fallback chain, thorough testing)  

**Ready to implement with minimal token waste!**

**Next Step**: Review and approve this plan before proceeding to Phase 0.

---

*Document End*
