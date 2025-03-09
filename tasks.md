## `auto-bump`

- Depends: _install

- **Usage**: `auto-bump`

Auto bump the version

## `install`

- Depends: install:pre-commit, _install

- **Usage**: `install`
- **Aliases**: `i`

Install dependencies and pre-commit hooks

## `install:pre-commit`

- **Usage**: `install:pre-commit`

Install pre-commit hooks

## `install:test`

- **Usage**: `install:test`

Install test dependencies only

## `lint`

- Depends: vulture, pyright, ruff:check

- **Usage**: `lint`
- **Aliases**: `l`

Lint the code

## `lint:pre-commit`

- Depends: vulture, pyright

- **Usage**: `lint:pre-commit`

Lint the code in pre-commit hook

## `pre-commit`

- Depends: install-pre-commit

- **Usage**: `pre-commit`

Run pre-commit checks

## `pyright`

- Depends: _install

- **Usage**: `pyright`

Run pyright

## `render:usage`

- **Usage**: `render:usage`

## `ruff:check`

- **Usage**: `ruff:check`

Check ruff formatting

## `ruff:fix`

- **Usage**: `ruff:fix`

Fix ruff errors

## `ruff:format`

- **Usage**: `ruff:format`

Format code

## `test`

- Depends: _install

- **Usage**: `test [test]`
- **Aliases**: `t`

Run tests

### Arguments

#### `[test]`

## `test:ci`

- Depends: install:test

- **Usage**: `test:ci <session>`

Run tests in CI

### Arguments

#### `<session>`

## `test:matrix`

- Depends: install:test

- **Usage**: `test:matrix`

Output test matrix for CI

## `test:py13`

- Depends: _install

- **Usage**: `test:py13 [test]`
- **Aliases**: `t13`

Run tests on python 3.13

### Arguments

#### `[test]`

## `test:update-snapshot`

- Depends: _install

- **Usage**: `test:update-snapshot`

Run snapshot-based tests and update snapshots

## `vulture`

- Depends: _install

- **Usage**: `vulture`

Run vulture
