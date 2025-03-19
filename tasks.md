## `auto-bump`

- Depends: _install

- **Usage**: `auto-bump`

Auto bump the version

## `ci:lint`

- **Usage**: `ci:lint`

Lint CI yaml files

## `ci:test`

- Depends: install:test

- **Usage**: `ci:test <session>`

Run tests in CI

### Arguments

#### `<session>`

## `ci:test-matrix`

- Depends: install:test

- **Usage**: `ci:test-matrix`

Output test matrix for CI

## `ci:test-sessions`

- Depends: install:test

- **Usage**: `ci:test-sessions`

Output test session names for CI

## `clean`

- **Usage**: `clean`
- **Aliases**: `c`

Clean working directory

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

- Depends: vulture, pyright, ruff:check, ruff:format:check

- **Usage**: `lint`
- **Aliases**: `l`

Lint the code

## `lint:pre-commit`

- Depends: vulture, pyright

- **Usage**: `lint:pre-commit`

Lint the code in pre-commit hook

## `pre-commit`

- Depends: install:pre-commit

- **Usage**: `pre-commit`

Run pre-commit checks

## `pyright`

- Depends: _install

- **Usage**: `pyright`

Run pyright

## `render:usage`

- **Usage**: `render:usage`

Generate tasks documentation

## `ruff:check`

- Depends: _install

- **Usage**: `ruff:check`

Check ruff formatting

## `ruff:fix`

- **Usage**: `ruff:fix`

Fix ruff errors

## `ruff:format`

- **Usage**: `ruff:format`

Format code

## `ruff:format:check`

- **Usage**: `ruff:format:check`

Format code

## `test`

- Depends: _install

- **Usage**: `test [test]`
- **Aliases**: `t`

Run tests

### Arguments

#### `[test]`

## `test:coverage`

- Depends: _install

- **Usage**: `test:coverage [test]`
- **Aliases**: `tc`

Run tests with coverage

### Arguments

#### `[test]`

## `test:integration`

- Depends: _install

- **Usage**: `test:integration [test]`
- **Aliases**: `ti`

Run integration tests

### Arguments

#### `[test]`

## `test:integration-all`

- Depends: _install

- **Usage**: `test:integration-all [test]`
- **Aliases**: `tia`

Run integration tests on all supported python versions

### Arguments

#### `[test]`

## `test:integration:coverage`

- Depends: _install

- **Usage**: `test:integration:coverage [test]`
- **Aliases**: `tic`

Run integration tests with coverage

### Arguments

#### `[test]`

## `test:unit`

- Depends: _install

- **Usage**: `test:unit [test]`
- **Aliases**: `tu`

Run unit tests

### Arguments

#### `[test]`

## `test:unit-all`

- Depends: _install

- **Usage**: `test:unit-all [test]`
- **Aliases**: `tua`

Run unit tests on all supported python versions

### Arguments

#### `[test]`

## `test:unit:coverage`

- Depends: _install

- **Usage**: `test:unit:coverage [test]`
- **Aliases**: `tuc`

Run unit tests with coverage

### Arguments

#### `[test]`

## `test:unit:no-extras`

- Depends: _install

- **Usage**: `test:unit:no-extras [test]`
- **Aliases**: `tug`

Run unit tests without extras dependencies

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
