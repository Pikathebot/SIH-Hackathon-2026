

def test_non_ascii_log_line_on_cp1252_stdout():
    """A redirected Windows stdout is cp1252; non-ASCII log text must not print a logging traceback."""
    import os
    import subprocess
    import sys
    from pathlib import Path
    code = ("from app.observability import configure_logging; import logging; configure_logging(); "
            "logging.getLogger('t').warning('query: %s', 'नदी → ✓')")
    env = {**os.environ, "PYTHONIOENCODING": "cp1252"}
    out = subprocess.run([sys.executable, "-c", code], cwd=Path(__file__).resolve().parents[1],
                         env=env, capture_output=True, timeout=60)
    assert b"Logging error" not in out.stderr, out.stderr.decode(errors="replace")
    assert "→".encode("utf-8") in out.stdout
