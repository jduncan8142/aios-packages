#!/usr/bin/env python3
"""Verify every package manifest's pinned `rev` resolves to a real tag.

For each `packages/*.toml`, this checks that the `rev` field names a git **tag**
that actually exists on the manifest's `source` repository. It exists to catch
drift like the historical `canvas-v0.1.1` pin, where the index referenced a tag
the source repo did not (or no longer) carried.

Resolution strategy
-------------------
* **GitHub sources** (`github.com/<owner>/<repo>`): resolved via the GitHub API
  (`gh api repos/<owner>/<repo>/git/matching-refs/tags/<rev>`). The API works
  for both public and private repos as long as the token in `GH_TOKEN` can read
  the repo.
* **Non-GitHub sources**: resolved with `git ls-remote --tags <source> <rev>`,
  which uses whatever credentials the environment provides.

Token note (important for CI)
-----------------------------
The component source repos (AiOSCanvas, AiOSFSS, …) are **private**, while this
index repo is public. The workflow's default `GITHUB_TOKEN` is scoped to *this*
repo only, so it cannot read the private sources — those lookups come back 404
(GitHub masks private repos as not-found for under-privileged tokens).

To resolve tags on the private sources, the workflow must run with a token that
can read them — e.g. a `SUBMODULES_TOKEN` secret (a fine-grained PAT or
org/app token with `contents:read` on the component repos). When a lookup fails
with an auth/visibility error, this script reports it as an **access** failure
distinct from a genuinely **missing** tag, so a misconfigured token is not
mistaken for drift.

Exit status: 0 if every manifest's rev resolves to a tag; 1 otherwise (missing
tags, access failures, or malformed manifests).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGES_DIR = REPO_ROOT / "packages"

GITHUB_URL = re.compile(
    r"^(?:https?://github\.com/|git@github\.com:)(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?/?$"
)


@dataclass
class Result:
    name: str
    rev: str
    source: str
    ok: bool
    detail: str


def parse_github(source: str) -> tuple[str, str] | None:
    """Return (owner, repo) for a GitHub source URL, else None."""
    m = GITHUB_URL.match(source.strip())
    if not m:
        return None
    return m.group("owner"), m.group("repo")


def resolve_github_tag(owner: str, repo: str, rev: str) -> Result:
    """Resolve `rev` as a tag on a GitHub repo via the API.

    Uses `matching-refs/tags/<rev>`, which returns an array of refs whose name
    starts with `<rev>`; we require an exact `refs/tags/<rev>` match so that a
    pin of `v0.1` does not spuriously match `v0.1.1`.
    """
    api = f"repos/{owner}/{repo}/git/matching-refs/tags/{rev}"
    proc = subprocess.run(
        ["gh", "api", api],
        capture_output=True,
        text=True,
    )
    name = f"{owner}/{repo}@{rev}"
    if proc.returncode != 0:
        stderr = proc.stderr.strip()
        # Distinguish "can't see the repo" (token scope) from "tag missing".
        lowered = stderr.lower()
        if any(s in lowered for s in ("http 404", "not found", "could not resolve to a repository")):
            return Result(
                name, rev, f"{owner}/{repo}", False,
                "source repo not found for the active token. If this source is "
                "private, the workflow needs a token with read access to it "
                "(see SUBMODULES_TOKEN in the workflow). Otherwise the source "
                "URL is wrong.",
            )
        if any(s in lowered for s in ("http 401", "http 403", "bad credentials", "forbidden")):
            return Result(
                name, rev, f"{owner}/{repo}", False,
                f"access denied resolving tags ({stderr}). The token cannot read "
                "this (private) source; provide SUBMODULES_TOKEN.",
            )
        return Result(name, rev, f"{owner}/{repo}", False, f"gh api error: {stderr}")

    try:
        refs = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError as exc:
        return Result(name, rev, f"{owner}/{repo}", False, f"unparseable gh api output: {exc}")

    wanted = f"refs/tags/{rev}"
    if any(ref.get("ref") == wanted for ref in refs):
        return Result(name, rev, f"{owner}/{repo}", True, "tag exists")
    # Refs came back but none is an exact tag match.
    near = ", ".join(sorted(r.get("ref", "") for r in refs)) or "(none)"
    return Result(
        name, rev, f"{owner}/{repo}", False,
        f"no tag named '{rev}' on the source (closest refs: {near}). "
        "Pin drift — update the manifest's rev or push the tag.",
    )


def resolve_git_ls_remote(source: str, rev: str, name: str) -> Result:
    """Resolve `rev` as a tag on a non-GitHub source via `git ls-remote`."""
    proc = subprocess.run(
        ["git", "ls-remote", "--tags", source, rev],
        capture_output=True,
        text=True,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )
    label = f"{name}@{rev}"
    if proc.returncode != 0:
        return Result(label, rev, source, False, f"git ls-remote failed: {proc.stderr.strip()}")
    # A matching tag prints a line "<sha>\trefs/tags/<rev>" (and maybe "^{}").
    if any(
        line.split("\t")[-1] in (f"refs/tags/{rev}", f"refs/tags/{rev}^{{}}")
        for line in proc.stdout.splitlines()
    ):
        return Result(label, rev, source, True, "tag exists")
    return Result(
        label, rev, source, False,
        f"no tag named '{rev}' on {source} (pin drift).",
    )


def check_manifest(path: Path) -> Result:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        return Result(path.name, "?", "?", False, f"cannot read manifest: {exc}")

    name = data.get("name", path.stem)
    source = data.get("source")
    rev = data.get("rev")
    if not source or not rev:
        return Result(name, rev or "?", source or "?", False, "manifest missing `source` or `rev`")

    gh = parse_github(source)
    if gh is not None:
        return resolve_github_tag(gh[0], gh[1], rev)
    return resolve_git_ls_remote(source, rev, name)


def main() -> int:
    if not PACKAGES_DIR.is_dir():
        print(f"::error::no packages/ directory at {PACKAGES_DIR}")
        return 1
    manifests = sorted(PACKAGES_DIR.glob("*.toml"))
    if not manifests:
        print("::error::no package manifests found under packages/")
        return 1

    results = [check_manifest(p) for p in manifests]
    failures = [r for r in results if not r.ok]

    for r in results:
        mark = "ok" if r.ok else "FAIL"
        print(f"[{mark}] {r.name}: rev '{r.rev}' on {r.source} — {r.detail}")
        if not r.ok:
            # GitHub Actions error annotation for the summary view.
            print(f"::error::{r.name}: rev '{r.rev}' does not resolve to a tag — {r.detail}")

    print()
    print(f"Checked {len(results)} manifest(s); {len(failures)} failing.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
