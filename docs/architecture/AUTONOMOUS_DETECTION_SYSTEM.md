# Autonomous Detection System - Design Document

## Overview

Design for a self-adaptive window detection system that uses runtime metrics analysis to automatically optimize method selection, recover from failures, and maintain reliable operation over extended periods.

---

## Theoretical Foundation

### Problem Classification

This is a **Multi-Armed Bandit (MAB) problem** where:
- **Arms** = Detection methods (Direct DBus, File-Based, etc.)
- **Reward** = Detection success + speed
- **Goal** = Maximize reward while handling environment changes

### Chosen Algorithms

**1. Circuit Breaker Pattern** (Netflix Hystrix)
- Immediately isolate failing methods
- Prevent cascade failures
- Auto-retry with backoff

**2. Exponential Weighted Moving Average (EWMA)**
- Track smoothed metrics (latency, success rate)
- React to trends, not noise
- Formula: `new_value = α * current + (1-α) * previous`

**3. Upper Confidence Bound (UCB1)**
- Balance exploitation (use best) vs exploration (test others)
- Guarantees eventual convergence to optimal
- Formula: `score = success_rate + c * sqrt(ln(total_attempts) / method_attempts)`

**4. Exponential Backoff Retry**
- Retry failed methods with increasing delays
- Prevents thrashing
- Formula: `wait_time = base_delay * 2^attempt_count`

---

## System Architecture

### Phase 1: Metrics Collection & Health Tracking (3 hours)

**Component**: `DetectionHealth` class

```python
import time
from dataclasses import dataclass
from typing import Dict, List
import statistics

@dataclass
class MethodStats:
    """Statistics for a single detection method."""
    name: str
    
    # Counters
    success_count: int = 0
    failure_count: int = 0
    timeout_count: int = 0
    exception_count: int = 0
    
    # Latency tracking (EWMA)
    avg_latency_ms: float = 0.0
    min_latency_ms: float = float('inf')
    max_latency_ms: float = 0.0
    
    # Recent samples for percentiles
    recent_latencies: List[float] = None
    max_recent_samples: int = 100
    
    # Circuit breaker state
    circuit_state: str = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
    circuit_open_until: float = 0.0
    consecutive_failures: int = 0
    
    # UCB1 tracking
    ucb_score: float = 0.0
    last_attempt_time: float = 0.0
    
    def __post_init__(self):
        if self.recent_latencies is None:
            self.recent_latencies = []
    
    @property
    def total_attempts(self) -> int:
        return self.success_count + self.failure_count
    
    @property
    def success_rate(self) -> float:
        if self.total_attempts == 0:
            return 0.0
        return self.success_count / self.total_attempts
    
    @property
    def p50_latency_ms(self) -> float:
        if not self.recent_latencies:
            return 0.0
        return statistics.median(self.recent_latencies)
    
    @property
    def p95_latency_ms(self) -> float:
        if not self.recent_latencies:
            return 0.0
        sorted_latencies = sorted(self.recent_latencies)
        idx = int(len(sorted_latencies) * 0.95)
        return sorted_latencies[idx] if idx < len(sorted_latencies) else sorted_latencies[-1]


class DetectionHealth:
    """
    Autonomous health tracking and adaptive behavior system.
    
    Implements:
    - Circuit Breaker Pattern (failure isolation)
    - EWMA smoothing (metric tracking)
    - UCB1 algorithm (exploration-exploitation)
    - Exponential backoff (retry logic)
    """
    
    # Configuration constants
    EWMA_ALPHA = 0.3  # Weight for new observations (0-1, higher = more reactive)
    CIRCUIT_OPEN_THRESHOLD = 3  # Failures before opening circuit
    CIRCUIT_OPEN_DURATION_S = 60  # Seconds circuit stays open
    CIRCUIT_HALF_OPEN_ATTEMPTS = 3  # Test attempts in half-open state
    UCB_EXPLORATION_PARAM = 2.0  # Higher = more exploration
    SLOW_METHOD_THRESHOLD_MS = 100  # Methods slower than this are penalized
    
    def __init__(self):
        self.method_stats: Dict[str, MethodStats] = {}
        self.total_detections = 0
        self.start_time = time.time()
    
    def get_or_create_stats(self, method_name: str) -> MethodStats:
        """Get stats for method, creating if needed."""
        if method_name not in self.method_stats:
            self.method_stats[method_name] = MethodStats(name=method_name)
        return self.method_stats[method_name]
    
    def record_success(self, method_name: str, latency_ms: float):
        """
        Record successful detection.
        
        Updates:
        - Success counters
        - EWMA latency
        - Circuit breaker (close if was open)
        - Recent latencies for percentiles
        """
        stats = self.get_or_create_stats(method_name)
        
        # Update counters
        stats.success_count += 1
        stats.consecutive_failures = 0
        self.total_detections += 1
        
        # Update latency with EWMA
        if stats.avg_latency_ms == 0:
            stats.avg_latency_ms = latency_ms
        else:
            stats.avg_latency_ms = (
                self.EWMA_ALPHA * latency_ms + 
                (1 - self.EWMA_ALPHA) * stats.avg_latency_ms
            )
        
        # Update min/max
        stats.min_latency_ms = min(stats.min_latency_ms, latency_ms)
        stats.max_latency_ms = max(stats.max_latency_ms, latency_ms)
        
        # Store for percentiles
        stats.recent_latencies.append(latency_ms)
        if len(stats.recent_latencies) > stats.max_recent_samples:
            stats.recent_latencies.pop(0)
        
        # Circuit breaker: close on success
        if stats.circuit_state == "HALF_OPEN":
            stats.circuit_state = "CLOSED"
            logger.info(f"✅ Circuit CLOSED for {method_name} after successful test")
        
        stats.last_attempt_time = time.time()
    
    def record_failure(self, method_name: str, failure_type: str = "generic"):
        """
        Record failed detection.
        
        Updates:
        - Failure counters
        - Circuit breaker (may open)
        - Consecutive failure tracking
        
        Args:
            failure_type: 'timeout', 'exception', or 'generic'
        """
        stats = self.get_or_create_stats(method_name)
        
        # Update counters
        stats.failure_count += 1
        stats.consecutive_failures += 1
        self.total_detections += 1
        
        if failure_type == "timeout":
            stats.timeout_count += 1
        elif failure_type == "exception":
            stats.exception_count += 1
        
        # Circuit breaker logic
        if stats.consecutive_failures >= self.CIRCUIT_OPEN_THRESHOLD:
            if stats.circuit_state == "CLOSED":
                stats.circuit_state = "OPEN"
                stats.circuit_open_until = time.time() + self.CIRCUIT_OPEN_DURATION_S
                logger.warning(
                    f"⚠️ Circuit OPEN for {method_name} after "
                    f"{stats.consecutive_failures} failures. "
                    f"Will retry in {self.CIRCUIT_OPEN_DURATION_S}s"
                )
        
        stats.last_attempt_time = time.time()
    
    def should_try_method(self, method_name: str) -> bool:
        """
        Check if method should be tried (circuit breaker check).
        
        Returns:
            True if method should be attempted, False if circuit is open
        """
        stats = self.get_or_create_stats(method_name)
        
        if stats.circuit_state == "CLOSED":
            return True
        
        if stats.circuit_state == "OPEN":
            # Check if enough time has passed to test again
            if time.time() >= stats.circuit_open_until:
                stats.circuit_state = "HALF_OPEN"
                logger.info(f"🔄 Circuit HALF_OPEN for {method_name}, testing...")
                return True
            return False
        
        if stats.circuit_state == "HALF_OPEN":
            # Still testing
            return True
        
        return False
    
    def calculate_ucb_scores(self) -> Dict[str, float]:
        """
        Calculate UCB1 scores for all methods.
        
        UCB1 formula:
            score = success_rate + c * sqrt(ln(total) / attempts)
        
        Where:
        - success_rate = exploitation (use what works)
        - sqrt term = exploration (try less-used methods)
        - c = exploration parameter (higher = more exploration)
        
        Returns:
            Dict mapping method names to UCB scores
        """
        if self.total_detections == 0:
            return {}
        
        scores = {}
        for name, stats in self.method_stats.items():
            if stats.total_attempts == 0:
                # New method: give it high score to try it
                scores[name] = float('inf')
            else:
                # UCB1 formula
                exploitation = stats.success_rate
                
                # Exploration bonus
                import math
                exploration = math.sqrt(
                    math.log(self.total_detections) / stats.total_attempts
                )
                
                # Speed penalty: penalize slow methods
                speed_penalty = 0
                if stats.avg_latency_ms > self.SLOW_METHOD_THRESHOLD_MS:
                    speed_penalty = (stats.avg_latency_ms - self.SLOW_METHOD_THRESHOLD_MS) / 1000
                
                ucb_score = exploitation + self.UCB_EXPLORATION_PARAM * exploration - speed_penalty
                scores[name] = ucb_score
                stats.ucb_score = ucb_score
        
        return scores
    
    def get_sorted_methods(self, method_names: List[str]) -> List[str]:
        """
        Sort methods by UCB score (adaptive priority).
        
        This implements the autonomous method selection.
        
        Returns:
            List of method names sorted by priority (best first)
        """
        ucb_scores = self.calculate_ucb_scores()
        
        # Sort by UCB score descending
        return sorted(
            method_names,
            key=lambda name: ucb_scores.get(name, 0),
            reverse=True
        )
    
    def get_health_summary(self) -> str:
        """Generate human-readable health summary."""
        if not self.method_stats:
            return "No detection attempts yet"
        
        runtime_hours = (time.time() - self.start_time) / 3600
        
        lines = [
            f"Detection Health Summary (Runtime: {runtime_hours:.1f}h)",
            f"Total Detections: {self.total_detections}",
            ""
        ]
        
        # Sort by success rate
        sorted_methods = sorted(
            self.method_stats.values(),
            key=lambda s: s.success_rate,
            reverse=True
        )
        
        for stats in sorted_methods:
            # Convert circuit state to user-friendly status
            if stats.circuit_state == "CLOSED":
                enabled_status = "✅ Enabled"
            elif stats.circuit_state == "OPEN":
                enabled_status = "❌ Disabled (recovering)"
            else:  # HALF_OPEN
                enabled_status = "🔄 Testing"
            
            lines.append(f"{stats.name}:")
            lines.append(f"  Status: {enabled_status}")
            lines.append(f"  Success Rate: {stats.success_rate*100:.1f}% ({stats.success_count}/{stats.total_attempts})")
            
            if stats.success_count > 0:
                lines.append(f"  Latency: avg={stats.avg_latency_ms:.1f}ms, p50={stats.p50_latency_ms:.1f}ms, p95={stats.p95_latency_ms:.1f}ms")
            
            if stats.consecutive_failures > 0:
                lines.append(f"  ⚠️ Consecutive Failures: {stats.consecutive_failures}")
            
            lines.append(f"  UCB Score: {stats.ucb_score:.3f}")
            lines.append("")
        
        return "\n".join(lines)
    
    def export_metrics(self) -> Dict:
        """Export metrics in structured format (for monitoring systems)."""
        return {
            'total_detections': self.total_detections,
            'runtime_seconds': time.time() - self.start_time,
            'methods': {
                name: {
                    'success_count': stats.success_count,
                    'failure_count': stats.failure_count,
                    'success_rate': stats.success_rate,
                    'avg_latency_ms': stats.avg_latency_ms,
                    'p50_latency_ms': stats.p50_latency_ms,
                    'p95_latency_ms': stats.p95_latency_ms,
                    'circuit_state': stats.circuit_state,
                    'ucb_score': stats.ucb_score,
                }
                for name, stats in self.method_stats.items()
            }
        }
```

---

### Phase 2: Integration with WindowMonitor (2 hours)

**Modified WindowMonitor** with autonomous behavior:

```python
class WindowMonitor:
    """Monitor with autonomous detection system."""
    
    def __init__(self, poll_interval=0.5, simulation_mode=False, 
                 detection_config=None):
        self.poll_interval = poll_interval
        self.simulation_mode = simulation_mode
        self.detection_config = detection_config or DetectionConfig()
        
        # Autonomous health system
        self.health = DetectionHealth()
        
        # Detection methods
        self.detection_methods = []
        self._register_detection_methods()
        self._initialize_detection_methods()
        
        # Periodic health check
        self.last_health_log = time.time()
        self.health_log_interval = 300  # Log every 5 minutes
    
    def get_active_window_info(self) -> Optional[WindowInfo]:
        """
        Get active window with autonomous method selection.
        
        Uses UCB1 algorithm to balance:
        - Exploitation: Use fastest, most reliable method
        - Exploration: Test other methods periodically
        """
        # Get available method names
        available_methods = [
            m for m in self.detection_methods 
            if m.available and self.health.should_try_method(m.name)
        ]
        
        if not available_methods:
            logger.warning("❌ No available detection methods!")
            return None
        
        # Autonomous sorting by UCB score
        sorted_names = self.health.get_sorted_methods([m.name for m in available_methods])
        method_order = {name: i for i, name in enumerate(sorted_names)}
        available_methods.sort(key=lambda m: method_order.get(m.name, 999))
        
        # Try methods in UCB-optimized order
        for method in available_methods:
            start_time = time.time()
            
            try:
                result = method.detect()
                latency_ms = (time.time() - start_time) * 1000
                
                if result is not None:
                    # Success!
                    self.health.record_success(method.name, latency_ms)
                    self.current_window_detection_method = method.name
                    
                    logger.debug(
                        f"✅ {method.name} succeeded in {latency_ms:.1f}ms "
                        f"(UCB score: {self.health.method_stats[method.name].ucb_score:.3f})"
                    )
                    
                    self._maybe_log_health()
                    return result
                else:
                    # Method returned None (no window or not applicable)
                    self.health.record_failure(method.name, "generic")
                    
            except subprocess.TimeoutExpired:
                latency_ms = (time.time() - start_time) * 1000
                self.health.record_failure(method.name, "timeout")
                logger.debug(f"⏱️ {method.name} timeout after {latency_ms:.0f}ms")
                
            except Exception as e:
                latency_ms = (time.time() - start_time) * 1000
                self.health.record_failure(method.name, "exception")
                logger.warning(f"❌ {method.name} exception: {e}")
        
        # All methods failed
        self._maybe_log_health()
        return None
    
    def _maybe_log_health(self):
        """Periodically log health summary."""
        if time.time() - self.last_health_log >= self.health_log_interval:
            logger.info(self.health.get_health_summary())
            self.last_health_log = time.time()
    
    def stop(self):
        """Stop monitoring and log final stats."""
        self.running = False
        
        # Log final health summary
        logger.info("=" * 60)
        logger.info("FINAL DETECTION HEALTH SUMMARY")
        logger.info("=" * 60)
        logger.info(self.health.get_health_summary())
        
        # Cleanup methods
        for method in self.detection_methods:
            if method.initialized:
                try:
                    method.cleanup()
                    logger.info(f"✅ Cleaned up {method.name}")
                except Exception as e:
                    logger.warning(f"⚠️ Cleanup failed for {method.name}: {e}")
```

---

## Autonomous Behaviors

### 1. **Automatic Failure Isolation** (Circuit Breaker)

**Scenario**: Direct DBus starts failing after KWin crash

```
Detection 1:  Direct DBus fails ❌ (consecutive_failures = 1)
Detection 2:  Direct DBus fails ❌ (consecutive_failures = 2)  
Detection 3:  Direct DBus fails ❌ (consecutive_failures = 3)
              → Circuit OPENS, method disabled for 60s
Detection 4:  Skips Direct DBus entirely ✅
              → Falls back to File-Based (12ms) ✅
...
After 60s:    Circuit → HALF_OPEN, tests Direct DBus
              → Success! Circuit CLOSES, Direct DBus back in rotation
```

**Benefit**: Prevents 3x 1s timeouts = instant 3s delay. Now: 3x 1s initially, then fast fallback.

---

### 2. **Adaptive Priority** (UCB1 Algorithm)

**Scenario**: System changes over time

```
Week 1:  Direct DBus works perfectly
         → High success rate → High UCB score → Tried first always ✅

Week 2:  KDE upgrade changes DBus API, Direct DBus starts failing sometimes
         → Lower success rate → Lower UCB score
         → File-Based tried more often (exploration)
         → System naturally migrates to File-Based ✅

Week 3:  KDE fixes bug, Direct DBus reliable again
         → Exploration occasionally tests Direct DBus
         → Success! UCB score increases
         → System migrates back to Direct DBus ✅
```

**Key**: No manual intervention needed, system adapts automatically!

---

### 3. **Speed Optimization** (EWMA Tracking)

**Scenario**: Method becomes slower over time

```
Day 1:   File-Based: avg 12ms ✅
Day 10:  File-Based: avg 15ms (disk getting full)
Day 20:  File-Based: avg 25ms (disk very full)
         → Speed penalty in UCB calculation
         → Journal method (20ms) now has better UCB score
         → System switches to Journal method ✅
```

---

### 4. **Graceful Degradation**

**Scenario**: Multiple methods fail

```
Plasma crash → All KWin methods fail
              → System tries each once
              → All circuits open
              → Only kdotool/xdotool remain ✅
              → Degraded but still functional
```

---

## Configuration

**config.yml extension**:
```yaml
window_detection:
  autonomous:
    enabled: true
    
    # Circuit breaker tuning
    circuit_breaker:
      failure_threshold: 3          # Failures before opening
      open_duration_seconds: 60     # Cooldown period
      half_open_attempts: 3         # Test attempts
    
    # UCB algorithm tuning
    ucb:
      exploration_parameter: 2.0    # Higher = more exploration
      slow_threshold_ms: 100        # Penalty threshold
    
    # EWMA smoothing
    ewma:
      alpha: 0.3                    # 0-1, higher = more reactive
    
    # Health logging
    health_log_interval_seconds: 300  # Log every 5 min
```

---

## Testing Strategy

### Unit Tests

```python
def test_circuit_breaker():
    """Test circuit opens after threshold failures."""
    health = DetectionHealth()
    
    # Record failures
    for _ in range(3):
        health.record_failure("method1")
    
    # Circuit should be open
    assert not health.should_try_method("method1")
    
    # Wait for cooldown
    time.sleep(61)
    
    # Should allow retry
    assert health.should_try_method("method1")
    
    # Success should close circuit
    health.record_success("method1", 10.0)
    assert health.should_try_method("method1")

def test_ucb_exploration():
    """Test UCB algorithm explores less-used methods."""
    health = DetectionHealth()
    
    # Method 1: heavily used, high success
    for _ in range(100):
        health.record_success("method1", 10.0)
    
    # Method 2: barely used, unknown quality
    health.record_success("method2", 15.0)
    
    scores = health.calculate_ucb_scores()
    
    # Method 2 should get exploration bonus
    assert scores["method2"] > scores["method1"]

def test_ewma_smoothing():
    """Test EWMA smooths latency spikes."""
    health = DetectionHealth()
    
    # Baseline
    health.record_success("method1", 10.0)
    assert health.method_stats["method1"].avg_latency_ms == 10.0
    
    # Spike
    health.record_success("method1", 100.0)
    
    # Should be smoothed (not 100)
    avg = health.method_stats["method1"].avg_latency_ms
    assert 10 < avg < 100
    
    # More normal values bring it back down
    for _ in range(10):
        health.record_success("method1", 10.0)
    
    assert health.method_stats["method1"].avg_latency_ms < 20
```

---

## Benefits Summary

| Feature | Algorithm | Benefit |
|---------|-----------|---------|
| **Failure Isolation** | Circuit Breaker | Prevents cascade failures, fast fallback |
| **Adaptive Priority** | UCB1 | Automatically finds best method, adapts to changes |
| **Speed Tracking** | EWMA | Smoothed metrics, trend detection |
| **Auto-Recovery** | Exponential Backoff | Methods auto-tested and restored |
| **Exploration** | UCB1 ε-greedy | Discovers when "bad" methods become good |
| **Observability** | Metrics Export | Production monitoring, debugging |

**Result**: Truly autonomous system that runs reliably for weeks/months without manual tuning!

---

## Implementation Timeline

| Phase | Component | Duration | Dependencies |
|-------|-----------|----------|--------------|
| **1a** | MethodStats dataclass | 30 min | None |
| **1b** | DetectionHealth class | 2 hours | 1a |
| **1c** | Health unit tests | 1 hour | 1b |
| **2a** | WindowMonitor integration | 1.5 hours | 1b |
| **2b** | Integration tests | 1 hour | 2a |
| **2c** | Config system | 30 min | 2a |
| **Total** | | **6.5 hours** | |

---

## Future Enhancements

### Phase 3: Advanced Analytics (Optional, +4 hours)

- **Anomaly Detection**: Detect unusual patterns (sudden latency spikes)
- **Predictive Failure**: Predict method failure before it happens
- **A/B Testing**: Automatically test new methods against production
- **Prometheus Export**: Real-time metrics for Grafana dashboards

---

*This design creates a production-grade, self-healing detection system using well-proven algorithms from distributed systems and reinforcement learning theory.*
