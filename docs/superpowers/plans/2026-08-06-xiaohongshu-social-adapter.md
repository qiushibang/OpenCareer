# Xiaohongshu Social Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add all public Xiaohongshu social-recruitment jobs.

**Architecture:** Parse complete list responses offline and drive signed pagination only through a fresh first-party browser page. Use a bounded multi-pass ID union for live ordering drift.

**Tech Stack:** Python 3.12, Playwright, pytest, FastMCP.

---

### Task 1: Parser

- [ ] Add a two-job fixture with complete duties and qualifications.
- [ ] Write failing parser and missing-field tests.
- [ ] Implement strict envelope, ID, status, title, location and JD mapping.

### Task 2: Drift-Safe Pagination

- [ ] Write failing tests for a recovered ID across passes and incomplete union.
- [ ] Implement stable-total, stable-content and exact-count validation.
- [ ] Limit the union to three full passes and 1,000 jobs.

### Task 3: Browser Transport

- [ ] Write a failing asyncio thread-isolation test.
- [ ] Open the official page in a fresh context.
- [ ] Capture the first list response and click the official Next control for
  every remaining page.
- [ ] Enforce official host and 110-second limits without reading signatures.

### Task 4: Acceptance

- [ ] Add pipeline and registry tests.
- [ ] Require live 875 unique complete jobs.
- [ ] Require MCP dry run `created=875`.
- [ ] Run full backend/Career, GUI and diff checks.
- [ ] Commit only Xiaohongshu files and direct docs/registry changes.
