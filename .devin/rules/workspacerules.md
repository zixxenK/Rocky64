---
trigger: always_on
---
---
auto_execution_mode: 3
---
# Autonomous ROS2 Engineering Workflow (PR-Driven Robotics System)

## 0. System Overview

This document defines a closed-loop autonomous engineering workflow for a ROS2-based robotics stack (Rock64 + Arduino + ESP32). The system operates as a PR-driven development agent that plans, implements, tests, and delivers changes through version control.

All outputs MUST be Git artifacts (branches, commits, PRs). No inline-only fixes are valid final outputs.

---

# 1. Execution Model

## 1.1 Delivery Contract

All completed work MUST be delivered as:

- Git commit(s)
- GitHub Pull Request
- CI-passing ROS2 package

The system MUST NOT:
- output partial code snippets as final results
- suggest fixes without implementation
- bypass CI validation

---

## 1.2 Workspace Isolation

All tasks execute in isolated environment:

1. Clone repository
2. Create feature branch
3. Implement changes
4. Run build and tests
5. Iterate until CI passes
6. Open Pull Request

---

## 1.3 Supported Interfaces

The system may interact with:

- GitHub (source control)
- ROS2 build system (`colcon`)
- CI pipelines
- Issue trackers (Linear/Jira-like)
- Slack/CLI triggers (optional orchestration layer)

No direct hardware interaction is allowed during development.

---

# 2. Task Ingestion Pipeline

## 2.1 Input Sources

Tasks may originate from:

- GitHub Issues
- CI failure reports
- Jira/Linear tickets
- CLI commands
- Slack-style commands
- Direct user prompts
- Code review comments
- Automated monitoring alerts
- Manual inspection requests
- Your own observations and suggestions
- Any other source of feedback or requirements

---

## 2.2 Task Normalization

Every task MUST be converted into a structured format:

- Objective
- Affected ROS2 nodes
- Affected topics
- Safety classification (LOW / MEDIUM / CRITICAL)
- Required validation steps
- Any additional context or requirements
- Your own observations and improvements with implementation suggestions

---

## 2.3 Planning Requirement

Before implementing changes, the system MUST:

- analyze ROS2 node graph impact
- identify affected topics and message types
- validate serial protocol constraints
- evaluate safety implications
- identify regression risks
- Your own observations and improvements with implementation suggestions

No implementation may proceed without planning for CRITICAL tasks.

---

# 3. ROS2 Architecture Rules

## 3.1 Source of Truth

- `src/robot_control/` is the ONLY active control layer
- `host_control/` is deprecated and MUST NOT be modified
- duplicated logic MUST be flagged and migrated, not extended

---

## 3.2 Node Requirements

All ROS2 nodes MUST:

- use publisher/subscriber architecture
- avoid blocking callbacks
- remain thread-safe
- be registered in `setup.py`
- match `package.xml` entry points

---

## 3.3 Deterministic Behavior Rule

Nodes MUST NOT:

- rely on implicit timing assumptions
- contain hidden state machines
- perform blocking I/O
- bypass ROS2 messaging layers

---

# 4. Serial Protocol & Hardware Safety

## 4.1 Serial Command Format

All Arduino communication MUST follow:
<ID,DIR,SPD>\n

Where:

- ID ∈ [0–255]
- DIR ∈ {F, B, L, R, S}
- SPD ∈ [0–255]

---

## 4.2 Hardware Access Rule

ONLY `arduino_bridge_node` may access serial hardware.

No exceptions:
- no debug bypass
- no direct serial writes
- no test-side hardware access

---

## 4.3 Failure Handling

On any of the following events:

- malformed serial message
- disconnect
- timeout violation

The system MUST:

1. immediately stop motors
2. enter SAFE_STOP state
3. flush command queues
4. attempt reconnection asynchronously

---

## 4.4 Watchdog Requirement (Firmware)

Arduino firmware MUST implement:

- `wdt_enable(WDTO_500MS)`
- heartbeat timeout ≤ 200ms
- missing heartbeat → immediate motor shutdown

---

# 5. Topic and Control Flow Integrity

## 5.1 Motion Flow

- `/cmd_vel` → raw motion intent
- `/cmd_vel_safe` → safety-validated velocity
- `/motor_cmd` → hardware-bound command string

No node may bypass this chain.

---

## 5.2 Emergency Override

- `/emergency_stop` overrides all motion topics
- forces zero velocity output
- halts serial transmission
- persists until reset condition cleared

---

# 6. Build and Deployment Rules

Every change MUST:

1. Modify `src/robot_control/`
2. Update `setup.py`
3. Validate `package.xml`
4. Execute: `colcon build --symlink-install`

---

## 6.1 Build Failure Policy

If build or tests fail:

- system MUST iterate fixes
- PR creation is forbidden until CI passes
- failing tests may not be ignored

---

# 7. Debugging and Analysis Policy

## 7.1 Evidence Classification

All findings MUST be categorized as:

- OBSERVED: logs, CI output, runtime data
- INFERRED: logical deductions

These must never be conflated.

---

## 7.2 Root Cause Priority

When diagnosing failures:

1. Safety system failure
2. Serial protocol violation
3. ROS2 node misconfiguration
4. Concurrency issues
5. Logical implementation errors

---

## 7.3 Legacy Code Handling

- `host_control/` is frozen
- duplication MUST be migrated, not extended
- migration MUST be documented in PR

---

# 8. Pull Request Requirements

Every PR MUST include:

## 8.1 Title
Clear subsystem description

## 8.2 Description
- change summary
- affected nodes
- affected topics
- safety impact

## 8.3 Validation Evidence
- build logs
- test results
- runtime verification (if applicable)

## 8.4 Risk Assessment
- LOW / MEDIUM / CRITICAL classification
- failure mode description

---

# 9. System Priority Hierarchy

When conflicts occur:

1. SAFETY (emergency stop, watchdog, motor shutdown)
2. HARDWARE INTEGRITY
3. SERIAL PROTOCOL CONSISTENCY
4. ROS2 ARCHITECTURE COMPLIANCE
5. CODE QUALITY

---

# 10. System Behavior Definition

This system does not operate as a suggestion engine.

It operates as a deterministic engineering agent that:

- decomposes tasks
- implements ROS2 changes
- validates hardware constraints
- enforces safety boundaries
- delivers PR-ready outputs
