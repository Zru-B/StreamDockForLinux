# Layered Architecture Migration - Implementation Plan

## Overview

This plan outlines the step-by-step migration from the current architecture to the new layered architecture. The migration will be incremental, test-driven, and minimize disruption to existing functionality.

---

## Migration Principles

1. **Incremental Migration** - Layer by layer, bottom-up
2. **Test-Driven** - Write tests before migrating code
3. **Parallel Operation** - New and old code coexist during transition
4. **No Big Bang** - Each phase is deployable
5. **Documentation First** - Update docs before implementation
6. **Workflow Integration** - Ensure LLM agents follow new architecture

---

## Phase 0: Preparation & Documentation

### 0.1 Architecture Documentation

**Goal:** Create comprehensive architecture reference for developers and LLM agents

**Tasks:**
- [ ] Create `docs/architecture/LAYERED_ARCHITECTURE.md`
  - Layer definitions and responsibilities
  - Component interaction diagrams
  - Design principles and patterns
  - Naming conventions
  
- [ ] Create `docs/architecture/MIGRATION_GUIDE.md`
  - Current vs. layered architecture mapping
  - Component transition plan
  - Breaking changes documentation
  
- [ ] Create `docs/architecture/COUPLING_DIAGRAM.md`
  - Visual dependency graphs
  - Layer interaction rules
  - Anti-patterns to avoid
  
- [ ] Update `docs/architecture/AGENT_KNOWLEDGE_BASE.md`
  - Reference layered architecture
  - Link to coupling diagrams
  - Migration status tracking

**Deliverables:**
- 4 architecture documents
- Mermaid diagrams embedded
- Clear examples for each layer

**Git Commit:**
- [ ] Commit Phase 0.1 changes
  ```bash
  unset GIT_AUTHOR_NAME GIT_AUTHOR_EMAIL GIT_COMMITTER_NAME GIT_COMMITTER_EMAIL
  git add docs/architecture/
  git commit -m "docs: Add layered architecture documentation

  - Add LAYERED_ARCHITECTURE.md with 4-layer design
  - Add MIGRATION_GUIDE.md for transition plan
  - Add COUPLING_DIAGRAM.md with visual dependency graphs
  - Update AGENT_KNOWLEDGE_BASE.md with architecture references"
  ```

---

### 0.2 Workflow Updates

**Goal:** Update all workflows to reference architectural requirements

**Tasks:**
- [ ] Update `.agent/workflows/feature-development.md`
  - Add step: "Review `LAYERED_ARCHITECTURE.md`"
  - Add step: "Identify target layer for new feature"
  - Add validation: "Check coupling diagram compliance"
  
- [ ] Update `.agent/workflows/refactoring.md`
  - Add step: "Verify changes align with layered architecture"
  - Add step: "Update component interaction diagrams if needed"
  
- [ ] Update `.agent/workflows/bug-fix.md`
  - Add step: "Identify which layer contains the bug"
  - Add step: "Verify fix doesn't violate layer boundaries"
  
- [ ] Update `.agent/workflows/documentation-audit.md`
  - Add verification: "Architecture docs match implementation"
  - Add verification: "Coupling diagrams are up-to-date"

**Deliverables:**
- 4 updated workflow files
- Annotated with architecture checkpoints
- LLM agents will automatically follow architecture

**Git Commit:**
- [ ] Commit Phase 0.2 changes
  ```bash
  unset GIT_AUTHOR_NAME GIT_AUTHOR_EMAIL GIT_COMMITTER_NAME GIT_COMMITTER_EMAIL
  git add .agent/workflows/
  git commit -m "chore: Update workflows for layered architecture compliance

  - Add architecture review steps to all workflows
  - Add layer identification requirements
  - Add coupling diagram validation checks
  - Ensure LLM agents follow architectural constraints"
  ```

---

### 0.3 Test Strategy Documentation

**Goal:** Define comprehensive test coverage strategy for new architecture

**Tasks:**
- [ ] Create `docs/testing/LAYER_TESTING_STRATEGY.md`
  - Infrastructure layer: Unit tests with mocks
  - Business logic layer: Pure logic tests (no mocks)
  - Orchestration layer: Integration tests
  - Application layer: End-to-end tests
  
- [ ] Create `docs/testing/COVERAGE_REQUIREMENTS.md`
  - Minimum coverage per layer (Infrastructure: 90%, Business: 95%, Orchestration: 85%)
  - Critical path identification
  - Edge cases to test
  
- [ ] Create `docs/testing/TEST_FIXTURES.md`
  - Mock interfaces for each layer
  - Reusable test data
  - Common test scenarios

**Deliverables:**
- 3 testing strategy documents
- Test templates for each layer
- Coverage targets defined

**Git Commit:**
- [ ] Commit Phase 0.3 changes
  ```bash
  unset GIT_AUTHOR_NAME GIT_AUTHOR_EMAIL GIT_COMMITTER_NAME GIT_COMMITTER_EMAIL
  git add docs/testing/
  git commit -m "docs: Add comprehensive testing strategy for layered architecture

  - Add LAYER_TESTING_STRATEGY.md with per-layer approach
  - Add COVERAGE_REQUIREMENTS.md with 90-95% targets
  - Add TEST_FIXTURES.md with reusable mocks and test data"
  ```

---

## Phase 1: Infrastructure Layer

### 1.1 HardwareInterface

**Goal:** Abstract USB/HID communication from current transport classes

**Tasks:**
- [ ] Create `src/StreamDock/infrastructure/hardware_interface.py`
  - Define abstract interface
  - Methods: `enumerate_devices()`, `open_device()`, `close_device()`, etc.
  
- [ ] Create `src/StreamDock/infrastructure/usb_hardware.py`
  - Implement using existing `LibUSBHIDAPI`
  - Wrapper around current transport layer
  
- [ ] **Write unit tests:** `tests/infrastructure/test_hardware_interface.py`
  - Test device enumeration
  - Test open/close operations
  - Test error handling
  - Mock USB subsystem
  - **Target coverage:** 90%

**Deliverables:**
- `HardwareInterface` abstract class
- `USBHardware` implementation
- 15+ unit tests
- 90% code coverage

**Git Commit:**
- [ ] Commit Phase 1.1 changes
  ```bash
  unset GIT_AUTHOR_NAME GIT_AUTHOR_EMAIL GIT_COMMITTER_NAME GIT_COMMITTER_EMAIL
  git add src/StreamDock/infrastructure/hardware_interface.py \
          src/StreamDock/infrastructure/usb_hardware.py \
          tests/infrastructure/test_hardware_interface.py
  git commit -m "feat(infrastructure): Add HardwareInterface abstraction layer

  - Add abstract HardwareInterface for USB/HID operations
  - Implement USBHardware wrapping LibUSBHIDAPI
  - Add 15+ unit tests with 90% coverage
  - Enable hardware layer testability"
  ```

---

### 1.2 SystemInterface

**Goal:** Abstract D-Bus and OS-level APIs

**Tasks:**
- [ ] Create `src/StreamDock/infrastructure/system_interface.py`
  - Define abstract interface
  - Methods: `monitor_screen_lock()`, `get_active_window()`, etc.
  
- [ ] Create `src/StreamDock/infrastructure/linux_system.py`
  - Implement using current D-Bus code from `LockMonitor`
  - Implement using current window detection from `WindowMonitor`
  
- [ ] **Write unit tests:** `tests/infrastructure/test_system_interface.py`
  - Test D-Bus connection mocking
  - Test window detection mocking
  - Test callback registration
  - **Target coverage:** 85%

**Deliverables:**
- `SystemInterface` abstract class
- `LinuxSystem` implementation  
- 12+ unit tests
- 85% code coverage

**Git Commit:**
- [ ] Commit Phase 1.2 changes
  ```bash
  unset GIT_AUTHOR_NAME GIT_AUTHOR_EMAIL GIT_COMMITTER_NAME GIT_COMMITTER_EMAIL
  git add src/StreamDock/infrastructure/system_interface.py \
          src/StreamDock/infrastructure/linux_system.py \
          tests/infrastructure/test_system_interface.py
  git commit -m "feat(infrastructure): Add SystemInterface for OS-level APIs

  - Add abstract SystemInterface for D-Bus and window management
  - Implement LinuxSystem extracting logic from LockMonitor/WindowMonitor
  - Add 12+ unit tests with 85% coverage
  - Decouple OS operations from business logic"
  ```

---

### 1.3 DeviceRegistry

**Goal:** Track devices by VID/PID/Serial, handle path changes transparently

**Tasks:**
- [ ] Create `src/StreamDock/infrastructure/device_registry.py`
  - Implement device tracking by ID (not path!)
  - Implement auto-reconnection on path change
  - Implement device state management
  
- [ ] **Write unit tests:** `tests/infrastructure/test_device_registry.py`
  - **Critical:** Test device path change scenario (the bug!)
  - Test device add/remove
  - Test reconnection logic
  - Test multiple devices
  - **Target coverage:** 95%
  
- [ ] **Write integration tests:** `tests/integration/test_device_reconnection.py`
  - Test actual USB device reconnection
  - Test path change detection
  - Test state preservation across reconnect

**Deliverables:**
- `DeviceRegistry` class
- 20+ unit tests
- 3+ integration tests
- 95% code coverage
- **Bug scenario covered!**

**Git Commit:**
- [ ] Commit Phase 1.3 changes
  ```bash
  unset GIT_AUTHOR_NAME GIT_AUTHOR_EMAIL GIT_COMMITTER_NAME GIT_COMMITTER_EMAIL
  git add src/StreamDock/infrastructure/device_registry.py \
          tests/infrastructure/test_device_registry.py \
          tests/integration/test_device_reconnection.py
  git commit -m "feat(infrastructure): Add DeviceRegistry with path-change handling

  - Track devices by VID/PID/Serial instead of USB path
  - Auto-reconnect when device path changes (fixes #XXX)
  - Add 20+ unit tests covering reconnection scenarios
  - Add 3+ integration tests for real USB reconnection
  - Achieve 95% coverage including critical bug scenario"
  ```

---

### 1.4 Infrastructure Layer Validation

**Tasks:**
- [ ] Update `docs/architecture/LAYERED_ARCHITECTURE.md`
  - Mark Infrastructure layer as "Implemented"
  - Update coupling diagram
  
- [ ] Run all infrastructure tests
  - Verify no dependencies on other layers
  - Verify mockability
  
- [ ] **Update workflows:** Add infrastructure layer examples
  
- [ ] Document lessons learned

**Git Commit:**
- [ ] Commit Phase 1.4 changes
  ```bash
  unset GIT_AUTHOR_NAME GIT_AUTHOR_EMAIL GIT_COMMITTER_NAME GIT_COMMITTER_EMAIL
  git add docs/architecture/LAYERED_ARCHITECTURE.md \
          docs/architecture/COUPLING_DIAGRAM.md \
          .agent/workflows/
  git commit -m "docs: Mark Infrastructure layer as complete

  - Update LAYERED_ARCHITECTURE.md with implementation status
  - Update coupling diagrams with actual dependencies
  - Add infrastructure examples to workflows
  - Document lessons learned from layer implementation"
  ```

---

## Phase 2: Business Logic Layer

### 2.1 SystemEventMonitor

**Goal:** Pure event dispatcher for system events

**Tasks:**
- [ ] Create `src/StreamDock/business/system_event_monitor.py`
  - Extract D-Bus monitoring from `LockMonitor`
  - Pure event routing (no device operations)
  - Handler registration system
  
- [ ] **Write unit tests:** `tests/business/test_system_event_monitor.py`
  - Test event dispatching
  - Test handler registration
  - Test multiple handlers
  - Mock SystemInterface
  - **Target coverage:** 95%
  
- [ ] **Write logical tests:** `tests/business/test_event_routing_logic.py`
  - Test complex event sequences
  - Test lock abort scenarios
  - Test race conditions

**Deliverables:**
- `SystemEventMonitor` class
- 15+ unit tests
- 5+ logical tests
- 95% code coverage

**Git Commit:**
- [ ] Commit Phase 2.1 changes
  ```bash
  unset GIT_AUTHOR_NAME GIT_AUTHOR_EMAIL GIT_COMMITTER_NAME GIT_COMMITTER_EMAIL
  git add src/StreamDock/business/system_event_monitor.py \
          tests/business/test_system_event_monitor.py \
          tests/business/test_event_routing_logic.py
  git commit -m "feat(business): Add SystemEventMonitor for event dispatching

  - Extract event monitoring from LockMonitor
  - Pure event routing without device coupling
  - Add 15+ unit tests with 95% coverage
  - Add 5+ logical tests for complex scenarios
  - Enable testable event handling"
  ```

---

### 2.2 LayoutManager

**Goal:** Manage layout selection and window rules

**Tasks:**
- [ ] Create `src/StreamDock/business/layout_manager.py`
  - Extract layout selection logic from current `Layout` and `WindowMonitor`
  - Implement rule matching engine
  - No device dependencies!
  
- [ ] **Write unit tests:** `tests/business/test_layout_manager.py`
  - Test layout selection
  - Test window rule matching
  - Test priority/fallback logic
  - **Target coverage:** 95%
  
- [ ] **Write logical tests:** `tests/business/test_layout_selection_rules.py`
  - Test complex window patterns
  - Test regex matching
  - Test edge cases

**Deliverables:**
- `LayoutManager` class
- 18+ unit tests
- 6+ logical tests
- 95% code coverage

**Git Commit:**
- [ ] Commit Phase 2.2 changes
  ```bash
  unset GIT_AUTHOR_NAME GIT_AUTHOR_EMAIL GIT_COMMITTER_NAME GIT_COMMITTER_EMAIL
  git add src/StreamDock/business/layout_manager.py \
          tests/business/test_layout_manager.py \
          tests/business/test_layout_selection_rules.py
  git commit -m "feat(business): Add LayoutManager for layout selection logic

  - Extract layout selection from Layout/WindowMonitor
  - Implement rule matching engine
  - Remove device dependencies from layout logic
  - Add 18+ unit tests with 95% coverage
  - Add 6+ logical tests for complex patterns"
  ```

---

### 2.3 ActionExecutor

**Goal:** Execute button actions without coupling to devices

**Tasks:**
- [ ] Create `src/StreamDock/business/action_executor.py`
  - Extract action execution from current `actions.py`
  - Plugin system for action types
  - Use SystemInterface for execution
  
- [ ] **Write unit tests:** `tests/business/test_action_executor.py`
  - Test command execution
  - Test application launching
  - Test layout switching
  - Mock SystemInterface
  - **Target coverage:** 90%
  
- [ ] **Write logical tests:** `tests/business/test_action_composition.py`
  - Test action chaining
  - Test conditional actions
  - Test error handling

**Deliverables:**
- `ActionExecutor` class
- 15+ unit tests
- 4+ logical tests
- 90% code coverage

**Git Commit:**
- [ ] Commit Phase 2.3 changes
  ```bash
  unset GIT_AUTHOR_NAME GIT_AUTHOR_EMAIL GIT_COMMITTER_NAME GIT_COMMITTER_EMAIL
  git add src/StreamDock/business/action_executor.py \
          tests/business/test_action_executor.py \
          tests/business/test_action_composition.py
  git commit -m "feat(business): Add ActionExecutor for button action handling

  - Extract action execution from actions.py
  - Add plugin system for extensible action types
  - Use SystemInterface for OS operations
  - Add 15+ unit tests with 90% coverage
  - Add 4+ logical tests for action composition"
  ```

---

### 2.4 Business Logic Layer Validation

**Tasks:**
- [ ] Verify zero dependencies on Infrastructure layer implementations
- [ ] Verify all business logic testable without mocks
- [ ] Update architecture documentation
- [ ] Update coupling diagrams
- [ ] Run full test suite (Infrastructure + Business)

**Git Commit:**
- [ ] Commit Phase 2.4 changes
  ```bash
  unset GIT_AUTHOR_NAME GIT_AUTHOR_EMAIL GIT_COMMITTER_NAME GIT_COMMITTER_EMAIL
  git add docs/architecture/
  git commit -m "docs: Mark Business Logic layer as complete

  - Verify zero infrastructure implementation dependencies
  - Confirm business logic is fully testable
  - Update architecture docs with implementation status
  - Update coupling diagrams
  - Document test results for Infrastructure + Business"
  ```

---

## Phase 3: Orchestration Layer

### 3.1 DeviceOrchestrator

**Goal:** Single coordination point for device operations + system events

**Tasks:**
- [ ] Create `src/StreamDock/orchestration/device_orchestrator.py`
  - Coordinate lock/unlock with device operations
  - Manage device state (brightness, layout, power mode)
  - Route button presses to ActionExecutor
  - Subscribe to SystemEventMonitor
  
- [ ] **Write integration tests:** `tests/integration/test_device_orchestrator.py`
  - Test lock/unlock flow
  - Test window change flow
  - Test device reconnection flow
  - Mock all dependencies (Registry, LayoutManager, etc.)
  - **Target coverage:** 85%
  
- [ ] **Write end-to-end tests:** `tests/e2e/test_orchestration_scenarios.py`
  - Test complete user scenarios
  - Test error recovery
  - Test edge cases

**Deliverables:**
- `DeviceOrchestrator` class
- 12+ integration tests
- 5+ end-to-end tests
- 85% code coverage

**Git Commit:**
- [ ] Commit Phase 3.1 changes
  ```bash
  unset GIT_AUTHOR_NAME GIT_AUTHOR_EMAIL GIT_COMMITTER_NAME GIT_COMMITTER_EMAIL
  git add src/StreamDock/orchestration/device_orchestrator.py \
          tests/integration/test_device_orchestrator.py \
          tests/e2e/test_orchestration_scenarios.py
  git commit -m "feat(orchestration): Add DeviceOrchestrator coordination layer

  - Single coordinator for device operations + system events
  - Manage device state across lock/unlock/reconnection
  - Route button presses to ActionExecutor
  - Add 12+ integration tests with 85% coverage
  - Add 5+ end-to-end scenario tests"
  ```

---

### 3.2 Orchestration Validation

**Tasks:**
- [ ] Verify DeviceOrchestrator is the ONLY component with cross-layer knowledge
- [ ] Verify event flows work end-to-end
- [ ] Update documentation with sequence diagrams
- [ ] Run full test suite (all layers)

**Git Commit:**
- [ ] Commit Phase 3.2 changes
  ```bash
  unset GIT_AUTHOR_NAME GIT_AUTHOR_EMAIL GIT_COMMITTER_NAME GIT_COMMITTER_EMAIL
  git add docs/architecture/
  git commit -m "docs: Mark Orchestration layer as complete

  - Verify DeviceOrchestrator is sole cross-layer coordinator
  - Add sequence diagrams for event flows
  - Update architecture docs with orchestration patterns
  - Document full layer test results"
  ```

---

## Phase 4: Application Layer

### 4.1 ConfigurationManager

**Goal:** Clean configuration loading separate from application logic

**Tasks:**
- [ ] Create `src/StreamDock/application/configuration_manager.py`
  - Extract from current `ConfigLoader`
  - Clean YAML parsing
  - Validation logic
  
- [ ] **Write unit tests:** `tests/application/test_configuration_manager.py`
  - Test YAML parsing
  - Test validation
  - Test error handling
  - **Target coverage:** 90%

**Deliverables:**
- `ConfigurationManager` class
- 10+ unit tests
- 90% code coverage

**Git Commit:**
- [ ] Commit Phase 4.1 changes
  ```bash
  unset GIT_AUTHOR_NAME GIT_AUTHOR_EMAIL GIT_COMMITTER_NAME GIT_COMMITTER_EMAIL
  git add src/StreamDock/application/configuration_manager.py \
          tests/application/test_configuration_manager.py
  git commit -m "feat(application): Add ConfigurationManager for config loading

  - Extract configuration logic from ConfigLoader
  - Clean YAML parsing with validation
  - Add 10+ unit tests with 90% coverage
  - Separate config from application lifecycle"
  ```

---

### 4.2 Application Bootstrap

**Goal:** Dependency injection container and application entry point

**Tasks:**
- [ ] Create `src/StreamDock/application/application.py`
  - Wire all components together
  - Dependency injection
  - Lifecycle management
  
- [ ] Update `src/main.py`
  - Use new `Application` class
  - Maintain backward compatibility (feature flag)
  
- [ ] **Write end-to-end tests:** `tests/e2e/test_application_lifecycle.py`
  - Test startup sequence
  - Test shutdown sequence
  - Test error scenarios

**Deliverables:**
- `Application` class
- Updated `main.py`
- 8+ end-to-end tests

**Git Commit:**
- [ ] Commit Phase 4.2 changes
  ```bash
  unset GIT_AUTHOR_NAME GIT_AUTHOR_EMAIL GIT_COMMITTER_NAME GIT_COMMITTER_EMAIL
  git add src/StreamDock/application/application.py \
          src/main.py \
          tests/e2e/test_application_lifecycle.py
  git commit -m "feat(application): Add Application bootstrap with DI container

  - Wire all layered components with dependency injection
  - Update main.py with feature flag for gradual rollout
  - Add lifecycle management (startup/shutdown)
  - Add 8+ end-to-end tests for application flow
  - Enable parallel operation of old and new architecture"
  ```

---

## Phase 5: Migration & Cleanup

### 5.1 Parallel Operation

**Goal:** Run old and new architecture side-by-side

**Tasks:**
- [ ] Add feature flag: `USE_LAYERED_ARCHITECTURE`
- [ ] Update `main.py` to support both modes
- [ ] Run both test suites in CI
- [ ] Monitor production behavior

**Git Commit:**
- [ ] Commit Phase 5.1 changes
  ```bash
  unset GIT_AUTHOR_NAME GIT_AUTHOR_EMAIL GIT_COMMITTER_NAME GIT_COMMITTER_EMAIL
  git add src/main.py .github/workflows/
  git commit -m "feat: Enable parallel operation of old and new architecture

  - Add USE_LAYERED_ARCHITECTURE feature flag
  - Run both test suites in CI
  - Enable safe rollback mechanism
  - Add production monitoring for both modes"
  ```

---

### 5.2 Deprecation

**Goal:** Mark old components as deprecated

**Tasks:**
- [ ] Add deprecation warnings to `LockMonitor`
- [ ] Add deprecation warnings to `DeviceManager`
- [ ] Update documentation with migration path
- [ ] Notify users of upcoming changes

**Git Commit:**
- [ ] Commit Phase 5.2 changes
  ```bash
  unset GIT_AUTHOR_NAME GIT_AUTHOR_EMAIL GIT_COMMITTER_NAME GIT_COMMITTER_EMAIL
  git add src/StreamDock/lock_monitor.py \
          src/StreamDock/device_manager.py \
          docs/
  git commit -m "chore: Deprecate old architecture components

  - Add deprecation warnings to LockMonitor and DeviceManager
  - Update docs with migration timeline
  - Add migration guide for users
  - Prepare for old code removal"
  ```

---

### 5.3 Removal

**Goal:** Remove old architecture code

**Tasks:**
- [ ] Delete `src/StreamDock/lock_monitor.py`
- [ ] Delete `src/StreamDock/device_manager.py`
- [ ] Delete old tests
- [ ] Remove feature flag
- [ ] Update all documentation

**Git Commit:**
- [ ] Commit Phase 5.3 changes
  ```bash
  unset GIT_AUTHOR_NAME GIT_AUTHOR_EMAIL GIT_COMMITTER_NAME GIT_COMMITTER_EMAIL
  git rm src/StreamDock/lock_monitor.py \
         src/StreamDock/device_manager.py \
         tests/test_lock_monitor.py \
         tests/test_device_manager.py
  git add src/main.py docs/
  git commit -m "refactor: Remove deprecated old architecture

  - Remove LockMonitor and DeviceManager classes
  - Remove old test files
  - Remove USE_LAYERED_ARCHITECTURE feature flag
  - Update all documentation to reflect new architecture
  - Complete migration to layered architecture"
  ```

---

## Phase 6: Enhanced Testing & Coverage

### 6.1 Coverage Enhancement

**Goal:** Achieve >90% test coverage across all layers

**Tasks:**
- [ ] Identify coverage gaps using `pytest-cov`
- [ ] **Write missing unit tests** for edge cases
  - Error handling paths
  - Boundary conditions
  - Concurrent operations
  
- [ ] **Write property-based tests** using `hypothesis`
  - Test device ID generation
  - Test layout matching logic
  - Test state transitions
  
- [ ] **Write performance tests**
  - Test device enumeration speed
  - Test event dispatching latency
  - Test memory usage

**Deliverables:**
- 30+ additional tests
- >90% overall coverage
- Performance benchmarks

**Git Commit:**
- [ ] Commit Phase 6.1 changes
  ```bash
  unset GIT_AUTHOR_NAME GIT_AUTHOR_EMAIL GIT_COMMITTER_NAME GIT_COMMITTER_EMAIL
  git add tests/
  git commit -m "test: Enhance coverage to >90% across all layers

  - Add 30+ tests for edge cases and error paths
  - Add property-based tests with hypothesis
  - Add performance benchmarks
  - Achieve >90% coverage target"
  ```

---

### 6.2 Integration Testing

**Goal:** Test real-world scenarios end-to-end

**Tasks:**
- [ ] **Write integration tests:** `tests/integration/test_device_lifecycle.py`
  - Device connect → configure → use → disconnect
  - Multiple devices simultaneously
  - Device hotplug during operation
  
- [ ] **Write integration tests:** `tests/integration/test_system_events.py`
  - Lock → unlock → layout restoration
  - Window change → layout switch → action execution
  - Lock during window transition
  
- [ ] **Write integration tests:** `tests/integration/test_error_recovery.py`
  - D-Bus connection failure → recovery
  - USB device disconnection → reconnection
  - Configuration reload

**Deliverables:**
- 15+ integration tests
- Real-world scenarios covered
- Error recovery validated

**Git Commit:**
- [ ] Commit Phase 6.2 changes
  ```bash
  unset GIT_AUTHOR_NAME GIT_AUTHOR_EMAIL GIT_COMMITTER_NAME GIT_COMMITTER_EMAIL
  git add tests/integration/
  git commit -m "test: Add comprehensive integration tests

  - Add 15+ integration tests for real-world scenarios
  - Test device lifecycle and hotplug
  - Test system events and state transitions
  - Test error recovery and resilience"
  ```

---

### 6.3 Regression Test Suite

**Goal:** Ensure no regressions from current behavior

**Tasks:**
- [ ] **Create regression tests:** `tests/regression/test_legacy_behavior.py`
  - Test all current features still work
  - Test configuration compatibility
  - Test device compatibility
  
- [ ] **Capture baseline behavior**
  - Screenshot comparisons
  - Timing comparisons
  - State comparisons

**Deliverables:**
- 20+ regression tests
- Baseline behavior captured
- Compatibility verified

**Git Commit:**
- [ ] Commit Phase 6.3 changes
  ```bash
  unset GIT_AUTHOR_NAME GIT_AUTHOR_EMAIL GIT_COMMITTER_NAME GIT_COMMITTER_EMAIL
  git add tests/regression/
  git commit -m "test: Add regression test suite for backward compatibility

  - Add 20+ regression tests
  - Capture baseline behavior
  - Verify configuration compatibility
  - Ensure no feature regressions"
  ```

---

## Phase 7: Documentation Finalization

### 7.1 Architecture Documentation

**Tasks:**
- [ ] Finalize `docs/architecture/LAYERED_ARCHITECTURE.md`
  - Add implementation notes
  - Add gotchas and lessons learned
  - Add troubleshooting guide
  
- [ ] Finalize `docs/architecture/COUPLING_DIAGRAM.md`
  - Verify diagrams match implementation
  - Add interaction sequence diagrams
  - Add state machine diagrams
  
- [ ] Update `docs/architecture/AGENT_KNOWLEDGE_BASE.md`
  - Remove references to old architecture
  - Add layered architecture patterns
  - Add component catalog

**Git Commit:**
- [ ] Commit Phase 7.1 changes
  ```bash
  unset GIT_AUTHOR_NAME GIT_AUTHOR_EMAIL GIT_COMMITTER_NAME GIT_COMMITTER_EMAIL
  git add docs/architecture/
  git commit -m "docs: Finalize layered architecture documentation

  - Add implementation notes and lessons learned
  - Update coupling diagrams to match implementation
  - Add sequence and state diagrams
  - Update AGENT_KNOWLEDGE_BASE with patterns"
  ```

---

### 7.2 Developer Documentation

**Tasks:**
- [ ] Create `docs/development/ADDING_NEW_FEATURES.md`
  - Step-by-step guide using new architecture
  - Examples for each layer
  - Testing requirements
  
- [ ] Create `docs/development/TESTING_GUIDE.md`
  - How to write tests for each layer
  - Mock object patterns
  - Integration test patterns
  
- [ ] Update `README.md`
  - Architecture overview
  - Quick start guide
  - Testing instructions

**Git Commit:**
- [ ] Commit Phase 7.2 changes
  ```bash
  unset GIT_AUTHOR_NAME GIT_AUTHOR_EMAIL GIT_COMMITTER_NAME GIT_COMMITTER_EMAIL
  git add docs/development/ README.md
  git commit -m "docs: Add developer guides for layered architecture

  - Add feature development guide with layer examples
  - Add comprehensive testing guide
  - Update README with architecture overview
  - Document best practices and patterns"
  ```

---

### 7.3 API Documentation

**Tasks:**
- [ ] Generate API docs using `pdoc` or `sphinx`
- [ ] Document all public interfaces
- [ ] Add examples for each component
- [ ] Publish to `docs/api/`

**Git Commit:**
- [ ] Commit Phase 7.3 changes
  ```bash
  unset GIT_AUTHOR_NAME GIT_AUTHOR_EMAIL GIT_COMMITTER_NAME GIT_COMMITTER_EMAIL
  git add docs/api/
  git commit -m "docs: Generate API documentation for all components

  - Generate API docs with pdoc/sphinx
  - Document all public interfaces
  - Add usage examples
  - Publish to docs/api/"
  ```

---

## Phase 8: Workflow & LLM Integration

### 8.1 Workflow Enhancement

**Goal:** Ensure all workflows reference and enforce architecture

**Tasks:**
- [ ] Add pre-flight checks to workflows
  ```markdown
  // turbo
  Before starting, verify:
  1. Read docs/architecture/LAYERED_ARCHITECTURE.md
  2. Identify target layer for changes
  3. Review coupling diagram constraints
  ```
  
- [ ] Add validation steps
  ```markdown
  After implementation:
  1. Verify no layer boundary violations
  2. Update coupling diagram if needed
  3. Run layer-specific tests
  ```
  
- [ ] Add architecture review checklist
  - Single Responsibility Principle: ✓
  - Dependency Inversion: ✓
  - Layer boundaries respected: ✓

**Git Commit:**
- [ ] Commit Phase 8.1 changes
  ```bash
  unset GIT_AUTHOR_NAME GIT_AUTHOR_EMAIL GIT_COMMITTER_NAME GIT_COMMITTER_EMAIL
  git add .agent/workflows/
  git commit -m "chore: Enhance workflows with architecture enforcement

  - Add pre-flight architecture review steps
  - Add validation for layer boundaries
  - Add architecture checklist
  - Ensure compliance in all workflows"
  ```

---

### 8.2 LLM Agent Training

**Goal:** Ensure LLM agents understand and follow architecture

**Tasks:**
- [ ] Update `docs/architecture/AGENT_KNOWLEDGE_BASE.md`
  - Add explicit architecture rules
  - Add anti-pattern examples
  - Add refactoring patterns
  
- [ ] Create workflow triggers
  - `/refactor` → Must check architecture first
  - `/feature` → Must identify layer first
  - `/bug-fix` → Must isolate layer first
  
- [ ] Add automated checks
  - Pre-commit hook: Layer boundary validation
  - CI check: Coupling diagram compliance
  - PR template: Architecture review checklist

**Git Commit:**
- [ ] Commit Phase 8.2 changes
  ```bash
  unset GIT_AUTHOR_NAME GIT_AUTHOR_EMAIL GIT_COMMITTER_NAME GIT_COMMITTER_EMAIL
  git add docs/architecture/AGENT_KNOWLEDGE_BASE.md \
          .github/workflows/ \
          .pre-commit-config.yaml \
          .github/pull_request_template.md
  git commit -m "chore: Configure LLM agents for architecture compliance

  - Add architecture rules to AGENT_KNOWLEDGE_BASE
  - Add workflow triggers for architecture awareness
  - Add pre-commit hooks for boundary validation
  - Add PR template with architecture checklist"
  ```

---

## Success Criteria

### Technical Metrics
- [ ] Zero coupling violations between layers
- [ ] >90% test coverage across all components
- [ ] All 14 existing tests pass
- [ ] All new tests (100+) pass
- [ ] No performance regression

### Architectural Metrics
- [ ] Each component has single responsibility
- [ ] Infrastructure layer has zero dependencies
- [ ] Business logic testable without mocks
- [ ] DeviceOrchestrator is only cross-layer component

### Quality Metrics
- [ ] Zero bugs introduced during migration
- [ ] Documentation complete and accurate
- [ ] All workflows updated
- [ ] LLM agents follow architecture

---

## Timeline Estimate

| Phase | Duration | Parallel? |
|-------|----------|-----------|
| Phase 0: Preparation | 1 week | No |
| Phase 1: Infrastructure | 2 weeks | No |
| Phase 2: Business Logic | 2 weeks | No |
| Phase 3: Orchestration | 1.5 weeks | No |
| Phase 4: Application | 1 week | No |
| Phase 5: Migration | 1 week | Partial |
| Phase 6: Enhanced Testing | 1.5 weeks | Yes |
| Phase 7: Documentation | 1 week | Yes |
| Phase 8: Workflows | 0.5 weeks | Yes |

**Total: ~9-10 weeks** (assuming single developer, can be parallelized with multiple developers)

---

## Risk Mitigation

### Risk: Breaking Existing Functionality
**Mitigation:** 
- Parallel operation with feature flag
- Comprehensive regression tests
- Gradual rollout

### Risk: Test Coverage Gaps
**Mitigation:**
- Test-driven development (tests first)
- Coverage requirements per phase
- Automated coverage reporting

### Risk: Documentation Drift
**Mitigation:**
- Update docs before implementation
- Automated doc validation in CI
- Workflow enforcement

### Risk: LLM Agents Ignore Architecture
**Mitigation:**
- Explicit rules in AGENT_KNOWLEDGE_BASE
- Workflow pre-flight checks
- Automated validation hooks

---

## Rollback Plan

If migration fails at any phase:
1. Disable feature flag (`USE_LAYERED_ARCHITECTURE=False`)
2. Revert to previous stable version
3. Keep new test suite (still valuable)
4. Analyze failure and adjust plan
5. Retry with lessons learned

---

## Next Steps

1. **Review this plan** with team
2. **Create tracking issues** for each phase
3. **Set up project board** for task management
4. **Begin Phase 0** (Preparation & Documentation)
5. **Weekly progress reviews**

---

## Appendix: Test Inventory

### Current Tests (14 files)
- `test_actions.py` → Migrate to `ActionExecutor` tests
- `test_config_loader.py` → Migrate to `ConfigurationManager` tests
- `test_device_manager.py` → Migrate to `DeviceRegistry` tests
- `test_lock_monitor.py` → Split across `SystemEventMonitor` + `DeviceOrchestrator` tests
- `test_window_monitor.py` → Migrate to `LayoutManager` tests
- Others remain mostly unchanged

### New Tests (Estimated 100+)
- Infrastructure layer: 47 tests
- Business logic layer: 48 tests
- Orchestration layer: 17 tests
- Application layer: 18 tests
- Integration/E2E: 23 tests
- Regression: 20 tests

**Total: ~173 tests** (12x increase in test coverage!)
