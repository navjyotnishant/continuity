# Security Policy

## Reporting a vulnerability

Continuity has no server, no database, and no network access (see
[`docs/intent/continuity.md`](docs/intent/continuity.md) and
[`specs/001-continuity/spec.md`](specs/001-continuity/spec.md) — FR-019). Its
attack surface is local: the `.continuity/` files it reads and writes on a
project's own filesystem, and the shell scripts that run as Claude Code hooks.

If you find a security issue — for example, a way for `.continuity/` content
to be interpreted as an instruction rather than trusted context (see spec.md
Q4/FR-018), a lock or atomic-write bug that corrupts state, or a secret-scan
bypass that lets a credential enter git history (see spec.md's Concerns
section) — report it privately rather than opening a public issue:

- Open a [GitHub Security Advisory](../../security/advisories/new) on this
  repository, or
- Email the maintainer at navjyotnishant@gmail.com with a description of the
  issue and, if possible, steps to reproduce it.

Please do not disclose the issue publicly until it has been addressed.

## Scope

In scope: the plugin's own scripts (`hooks/`, `commands/`, `lib/`) and its
handling of `.continuity/` content. Out of scope: vulnerabilities in Claude
Code itself, or in the user's own project code that Continuity happens to run
alongside.

## Supported versions

This project is pre-1.0 and has no long-term-support branches yet. Security
fixes land on the latest released version.
