# Contributing to FluentAgent

## Workflow

1. Fork the repository.
2. Create a feature branch from `main`.
3. Make focused changes with clear commit messages.
4. Run tests and lint locally.
5. Open a pull request with a concise summary and validation output.

## Multi-Agent Development

This project follows a strict multi-agent workflow. Before editing, review `AGENTS.md` and follow:

- Branch ownership rules
- File scope restrictions per agent
- Merge/dependency order
- Stop conditions

If your task requires files outside your assigned scope, stop and document it per `AGENTS.md`.

## Testing Requirements

Run these checks before opening a PR:

```bash
pytest tests/ -v
ruff check src/ tests/
```

All checks must pass.

## Code Style

- Use Python type hints consistently.
- Keep line length at 100 characters.
- Prefer clear, explicit logic over hidden behavior.
- Follow existing project structure and naming patterns.
