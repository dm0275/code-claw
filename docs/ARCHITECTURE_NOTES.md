# Architecture Notes

This document captures small but important implementation rules that should stay consistent as the codebase grows.

## Model Types

CodeClaw intentionally uses both Pydantic `BaseModel` types and Python `dataclass` types, but they serve different purposes.

### Use `BaseModel` for:

- API request models
- API response models
- persisted domain records
- objects that need validation
- objects that need serialization or alias handling

Current examples:

- `Project`
- `Task`
- `Run`
- `TaskDetail`
- `TaskCreate`
- `ApprovalRequest`

### Use `dataclass` for:

- internal runtime-only objects
- temporary execution state
- helper result containers that never cross the API boundary
- objects that do not need Pydantic validation or serialization

Current examples:

- `TaskWorkspace`
- `CodexCliResult`

## Rule Of Thumb

If an object crosses the HTTP boundary or is treated as stored application state, use `BaseModel`.

If an object exists only inside the service layer during one execution flow, use `dataclass`.

## What To Avoid

- Do not mix `BaseModel` and `dataclass` arbitrarily within the same layer.
- Do not use `BaseModel` for short-lived internal helper objects unless validation or serialization is actually needed.
- Do not use `dataclass` for request or response payloads.
