# Zhipu Campus Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Register the complete Zhipu campus source and document why social remains disabled.

**Architecture:** Parameterize the proven Moka DOM transport and add a Zhipu-specific pure metadata parser.

**Tech Stack:** Python 3.12, Playwright, pytest, FastMCP.

---

### Task 1: Fixtures And Parser

- [ ] Add social and campus card fixtures.
- [ ] Write failing metadata, pipeline and registry tests.
- [ ] Parse team, employment type, optional category and location without title inference.

### Task 2: Shared Transport

- [ ] Parameterize the Kimi Moka transport by entry URL.
- [ ] Extract each rendered page atomically.
- [ ] Re-run all Kimi tests to prove behavior is unchanged.

### Task 3: Acceptance

- [ ] Confirm campus 19/19 complete and social has 3 incomplete JDs.
- [ ] Register only `zhipu-campus`.
- [ ] Require live 19 unique jobs and MCP dry run `created=19`.
- [ ] Run full backend/Career, GUI and diff checks.
