# Atomic Write Helper

The `core.io.atomic_write` utilities guarantee crash-safe writes by following a strict sequence:

1. Create a temporary file in the target directory. This keeps the temp file on the same filesystem as the destination so `os.replace` is truly atomic.
2. Invoke the user-provided writer, flush the handle, and call `os.fsync` to ensure file contents reach disk.
3. Atomically replace the destination via `os.replace`.
4. Optionally sync the parent directory (best effort). On Linux and other POSIX platforms this persists the rename; on Windows the directory sync is skipped if not supported.

Portability notes:

- The helper always uses `os.replace`, which is atomic on both Linux and Windows when source and destination are on the same filesystem.
- Directory fsync can raise `OSError` on Windows; failures are logged at DEBUG and ignored because NTFS flushes metadata automatically.
- All temporary files are deleted if any step fails, leaving the destination either untouched (when it existed) or absent (on first write).

Use `atomic_write_text` and `atomic_write_bytes` for the common string/bytes cases, or `atomic_write` for custom writers.
