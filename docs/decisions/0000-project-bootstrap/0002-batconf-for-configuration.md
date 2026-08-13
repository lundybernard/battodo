# 0002 — batconf for configuration

Status: Accepted
Date: 2026-08-07

## Context

BatTodo needs layered configuration (list source paths, time windows,
category rules; defaults < config file < environment < CLI). The author
maintains batconf and wants a fresh-project evaluation of it.

## Decision

Use batconf for all runtime configuration from the first feature onward.

## Options

### Option 1 — batconf
- [pro] Dogfooding on a greenfield project is a stated project goal
- [pro] Layered lookup matches the composable-list-source requirement (R6)
- [con] Possible friction on a tiny CLI; that friction is itself data

### Option 2 — stdlib (argparse defaults + tomllib)
- [pro] Zero dependencies, trivially simple
- [con] Produces no batconf evaluation signal; hand-rolls layering batconf already does

## Rationale

Evaluating batconf is a primary project goal, so the config layer is not
a place to minimize dependencies.

## Consequences

- batconf pain points get filed as upstream issues rather than worked
  around.
- Config schema lives in code per batconf conventions.
