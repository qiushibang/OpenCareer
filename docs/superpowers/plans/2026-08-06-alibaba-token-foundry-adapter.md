# Alibaba Token Foundry Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the official Token Foundry social-recruitment source.

**Architecture:** Use a parameterized Alibaba business scope, a pure JSON parser and a fresh Playwright first-party context. Register only the scope that passes live and MCP acceptance.

**Tech Stack:** Python 3.12, Playwright, pytest, FastMCP.

---

### Task 1: Parser

- [ ] Add a two-job complete-JD fixture.
- [ ] Write failing parser tests for IDs, locations, duties and requirements.
- [ ] Implement `parse_alibaba_page()` with strict envelope and field checks.
- [ ] Verify missing requirements fail and valid fixtures pass.

### Task 2: Browser Transport

- [ ] Write a failing asyncio thread-isolation test.
- [ ] Open the official position page in a fresh context and capture its
  `/position/search` request.
- [ ] Reissue pagination only inside that context with `pageSize=500`.
- [ ] Enforce host, HTTP, total, page and 110-second limits.

### Task 3: Pipeline And Registry

- [ ] Write failing pipeline and default-registry tests.
- [ ] Implement `AlibabaCareersAdapter(ALIBABA_TONGYI_SCOPE)`.
- [ ] Run focused tests and require all pass.

### Task 4: Acceptance

- [ ] Run live Adapter and require 61 unique complete jobs.
- [ ] Run MCP dry run and require `created=61`.
- [ ] Run full Career/backend, GUI and diff checks.
- [ ] Commit only Token Foundry source files and direct docs/registry changes.
