# tidyq design

## Goal

A task queue for apps that run on one machine: no broker, no separate service, one SQLite
file. Good for background jobs in small web apps, scripts and desktop tools.

## Core

- `Queue(path)`: opens or creates the queue file.
- `@queue.task`: registers a function; calling `.delay()` enqueues it.
- `queue.work()`: runs a worker loop in this process.
- Retries with exponential backoff and jitter; a dead letter table after the last try.

## Rules

1. The core has no dependencies outside the standard library.
2. Every public function is typed and documented.
3. Breaking changes only in major versions, each with a migration note.

## Windows

SQLite file locking differs on Windows, so the store takes a row in a lock table instead of
relying on file locks.
