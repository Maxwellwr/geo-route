# Tag-driven Release Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace source-controlled package versions and tag-triggered publishing with tag-derived versions and an explicit main-branch publish dispatch.

**Architecture:** PR CI builds with a technical version only. Merging a PR creates the next patch GitHub Release, then explicitly dispatches a main-branch publish workflow that checks out the release tag and deploys the package/feed. Manual releases use a small relay workflow to dispatch the same publisher.

**Tech Stack:** GitHub Actions, GitHub CLI, Bash, Entware IPK packaging.

**Spec:** `docs/superpowers/specs/2026-08-28-tag-driven-release-design.md`

## Global Constraints

- Default branch: `main`.
- Package versions are derived only from release tags `vMAJOR.MINOR.PATCH`.
- Pages deployment executes from `workflow_dispatch` on `main`.
- PR-only technical build version: `0.0.0`.
- Bootstrap tag before merge: `v0.1.6`.

---

### Task 1: Make package metadata versionless

**Files:**
- Create: `package/geo-route/CONTROL/control.in`
- Delete: `package/geo-route/CONTROL/control`
- Modify: `package/geo-route/build-ipk.sh`

**Interfaces:**
- Consumes: environment variable `GEO_ROUTE_VERSION=X.Y.Z`.
- Produces: staged `CONTROL/control` with injected `Version: X.Y.Z`.

- [ ] Create `control.in` without a Version field.
- [ ] Make `build-ipk.sh` fail when `GEO_ROUTE_VERSION` is missing or malformed.
- [ ] Copy `control.in` to staged `control` and inject the version.
- [ ] Update all control-file copy references.
- [ ] Verify a `0.0.0` test build succeeds in CI.

### Task 2: Split PR CI from publishing

**Files:**
- Modify: `.github/workflows/ipk.yml`

**Interfaces:**
- Consumes: pull requests targeting `main`.
- Produces: test/build status only.

- [ ] Keep PR trigger.
- [ ] Remove main/tag publishing behavior.
- [ ] Build with `GEO_ROUTE_VERSION=0.0.0`.
- [ ] Keep importer unit tests.

### Task 3: Add tag publisher

**Files:**
- Create: `.github/workflows/publish.yml`

**Interfaces:**
- Consumes: workflow-dispatch input `tag=vX.Y.Z`.
- Produces: release IPK asset and GitHub Pages feed.

- [ ] Validate tag syntax and derive version.
- [ ] Checkout the exact tag.
- [ ] Run tests and package build using the derived version.
- [ ] Upload the package to the matching GitHub Release with `--clobber`.
- [ ] Upload/deploy Pages artifact.

### Task 4: Add automatic release creator

**Files:**
- Create: `.github/workflows/release.yml`

**Interfaces:**
- Consumes: merged PR into `main`.
- Produces: next patch GitHub Release and a `workflow_dispatch` of `publish.yml` on `main`.

- [ ] Serialize releases with concurrency.
- [ ] Fetch all tags and compute next patch version.
- [ ] Create release targeting current main commit.
- [ ] Dispatch `publish.yml` with `--ref main -f tag=<new tag>`.

### Task 5: Add manual-release relay

**Files:**
- Create: `.github/workflows/release-published.yml`

**Interfaces:**
- Consumes: manually published release.
- Produces: a `workflow_dispatch` of `publish.yml` on `main`.

- [ ] Ignore releases authored by `github-actions[bot]`.
- [ ] Validate/forward the release tag.
- [ ] Dispatch publisher on `main`.

### Task 6: Verify and bootstrap

**Files:** none.

- [ ] Run PR CI and confirm tests/build pass.
- [ ] Review workflow YAML and PR diff.
- [ ] Create bootstrap tag `v0.1.6` on current `main` without publishing.
- [ ] Confirm latest tag baseline is `v0.1.6`.
