"""Read the lister's actual error(s) via the modern TD API.

Run in TD textport:
  exec(open('/Users/jp/Documents/GitHub/vCon/toe/probe_lister_error.py', encoding='utf-8').read())
"""
q = op('/project1/vcon/panel/queue')
if q is None:
    print('queue not found')
    raise SystemExit()

print(f"=== lister {q.path} ===")

# TD 2025+ replaced .error with .errors (a list) and addError
try:
    errs = q.errors
    if errs:
        for i, e in enumerate(errs):
            print(f"  error[{i}]: {e}")
    else:
        print("  errors: (empty list — no live errors)")
except Exception as exc:
    print(f"  .errors failed: {exc}")

# Some builds expose the last cook error via a different path
try:
    msg = q.lastErrorMessage
    if msg:
        print(f"  lastErrorMessage: {msg}")
except Exception:
    pass

# Try cooking it manually and catch what comes out
try:
    q.cook(force=True)
    print("  manual cook: succeeded (no error raised)")
except Exception as exc:
    print(f"  manual cook raised: {type(exc).__name__}: {exc}")