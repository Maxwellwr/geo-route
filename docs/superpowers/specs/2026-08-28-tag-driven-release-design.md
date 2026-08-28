# Tag-driven release and Pages publish design

## Goal

Make GitHub Release tags the only package-version source, automatically create a patch release after a PR is merged into `main`, and publish the resulting IPK/feed to GitHub Pages without relying on a tag-triggered Pages deployment.

## Constraints

- The repository default branch is `main`.
- A release/tag created by a workflow using `GITHUB_TOKEN` must not be expected to trigger another ordinary event workflow.
- Pages publication must run from a workflow dispatched on `main`; that workflow explicitly checks out the release tag.
- Package version must not be stored in source files.
- Existing package `0.1.6` must not be followed by a lower version. Bootstrap tag `v0.1.6` is required before merging this PR.
- Pull-request CI builds a non-published package using technical version `0.0.0`.

## Workflows

### PR CI

`.github/workflows/ipk.yml` runs on pull requests to `main`.

It:
1. runs unit tests;
2. builds the package with `GEO_ROUTE_VERSION=0.0.0`;
3. does not upload a release asset;
4. does not deploy Pages.

### Automatic release after merge

`.github/workflows/release.yml` runs on `pull_request.closed` for `main` and only proceeds when the PR was merged.

It:
1. checks out `main` with full tag history;
2. finds the highest semantic tag matching `vMAJOR.MINOR.PATCH`;
3. increments PATCH;
4. creates a GitHub Release and tag targeting current `main`;
5. explicitly dispatches `publish.yml` with `ref=main` and the created tag.

A concurrency group serializes release creation to prevent two merged PRs from choosing the same next version.

### Manual release

`.github/workflows/release-published.yml` listens for a manually published GitHub Release.

It dispatches `publish.yml` on `main`, passing `github.event.release.tag_name`.

Releases created by `github-actions[bot]` are ignored here because the automatic-release workflow already dispatches publishing directly.

### Publish

`.github/workflows/publish.yml` is triggered only via `workflow_dispatch`.

Input:
- `tag`: required, format `vMAJOR.MINOR.PATCH`.

It:
1. validates the tag;
2. derives package version by removing the leading `v`;
3. checks out `refs/tags/<tag>`;
4. runs tests;
5. builds the package with `GEO_ROUTE_VERSION=<derived version>`;
6. uploads/clobbers the IPK asset on that GitHub Release;
7. uploads the feed as a Pages artifact;
8. deploys Pages in a separate deploy job.

Because the workflow itself is dispatched with `ref=main`, Pages policy sees a main-branch workflow execution even though source checkout uses the tag.

## Package metadata

`package/geo-route/CONTROL/control.in` is a template and contains no `Version:` line.

`build-ipk.sh` requires `GEO_ROUTE_VERSION`, validates `X.Y.Z`, copies `control.in` to the staging control file, and injects `Version: X.Y.Z` during the build.

No release version remains committed in source.

## Bootstrap

Before merging the PR that introduces this workflow, create tag `v0.1.6` on the current `main` commit without publishing/building it. Then the first merged PR creates `v0.1.7`.
