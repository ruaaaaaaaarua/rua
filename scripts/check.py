"""One fail-fast gate; never installs packages or touches the user's data directory."""
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
VENV = ROOT / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
PYTHON = os.environ.get('CHECK_PYTHON') or (str(VENV) if VENV.exists() else sys.executable)
NPM = 'npm.cmd' if os.name == 'nt' else 'npm'


def main():
    steps = [
        ('Python types (models, knowledge, images, prompts)', [PYTHON, '-m', 'mypy']),
        ('JavaScript types (domain, API)', [NPM, '--prefix', 'web', 'run', 'typecheck']),
        ('Python correctness lint', [PYTHON, '-m', 'ruff', 'check', 'app', 'tests', 'scripts']),
        ('JavaScript correctness lint', [NPM, '--prefix', 'web', 'run', 'lint']),
        ('Knowledge integrity', [PYTHON, '-m', 'app.validate_knowledge']),
        ('Backend regression', [PYTHON, '-m', 'pytest', '-q']),
        ('Frontend regression', [NPM, '--prefix', 'web', 'test']),
        ('Production frontend build', [NPM, '--prefix', 'web', 'run', 'build']),
        ('Browser regression against built app', [NPM, '--prefix', 'web', 'run', 'test:e2e']),
    ]
    env = {**os.environ, 'CHECK_PYTHON': PYTHON}
    for title, command in steps:
        print(f'\n== {title} ==', flush=True)
        subprocess.run(command, cwd=ROOT, env=env, check=True)
    print('\nAll engineering checks passed.', flush=True)


if __name__ == '__main__':
    try:
        main()
    except (subprocess.CalledProcessError, OSError) as exc:
        print(f'Check failed: {exc}', file=sys.stderr)
        sys.exit(1)
