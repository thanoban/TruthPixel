# Testing and Development Workflow

## What this module is

This guide explains how to work on the project safely.

It covers:

- what to test
- how to run tests
- how to think about runtime vs training
- how to avoid common confusion

## 1. There are three kinds of work here

### Runtime/backend work

Examples:

- API changes
- auth changes
- analyzer runtime behavior
- storage logic

### ML/training work

Examples:

- dataset handling
- model training
- feature extraction
- export artifact changes

### Frontend work

Examples:

- webapp UI
- dashboard UI
- request/response rendering

## 2. Main test suites

### Backend tests

Location:

- `backend/tests/`

These cover:

- API behavior
- persistence
- auth
- async queue logic
- observability
- analyzers and pipeline behavior

### ML tests

Location:

- `ml/tests/`

These cover:

- augmentation
- dataset logic
- fusion feature extraction
- export/training helpers
- checkpoint metadata

## 3. Main verification command

Most reliable full check:

```bash
pytest -c pytest.ini
```

This runs:

- backend tests
- ML tests

## 4. Frontend verification

For frontend, the important build checks are:

```bash
cd webapp
npm run build

cd dashboard
npm run build
```

Why builds matter:

- type issues often appear there
- route/build config issues often appear there
- deployment safety depends on successful build, not only dev mode

## 5. Why test isolation matters

TruthPixel has real optional integrations:

- Vertex
- local L1 checkpoint
- TruFor
- Sightengine

Tests should not accidentally hit live external dependencies unless explicitly intended.

That is why test config isolation matters so much in this repo.

## 6. Development mindset

When changing code, ask:

1. Is this runtime behavior or training behavior?
2. Does it change a contract?
3. Does it need docs updated too?
4. Does it affect env/config?
5. Does it require new tests?

## 7. Good development workflow

If you are still getting oriented:

### Step 1

Read docs first.

### Step 2

Run tests before editing.

### Step 3

Change one area at a time.

### Step 4

Re-run the smallest relevant tests first.

### Step 5

Run the broader verification gate after.

This is much easier than changing many unrelated things at once.

## 8. Good file-reading order before edits

If you want to change runtime behavior:

1. relevant doc
2. `config.py`
3. route file or pipeline file
4. module implementation
5. existing tests

If you want to change training behavior:

1. `ML_PLAN.md`
2. relevant `ml/` module
3. runtime consumer of exported artifact
4. tests

## 9. Common mistakes to avoid

### Mistake: mixing training and runtime logic

Do not put training workflows into runtime request path.

### Mistake: duplicating logic in frontend

Frontend should render backend outputs, not invent its own rules.

### Mistake: trusting docs more than code

Docs help, but runtime truth lives in:

- `config.py`
- `main.py`
- `graph/build.py`
- tests

### Mistake: changing schema without understanding persistence flow

Storage changes can affect:

- API responses
- audit logs
- dashboards
- async jobs
- future training exports

## 10. What “done” means in this repo

A good change usually includes:

- code
- tests or verification
- doc updates if behavior changed

That is especially important in a project like TruthPixel because it has:

- ML logic
- product logic
- operational logic

All three need to stay aligned.
