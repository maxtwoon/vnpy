# sync-guardian:managed:v3
"""Run an unchanged checker against Git index contents in an isolated local clone.

Usage: python tools/staged_check.py -- python tools/guardian.py check
Whole working-tree checks remain available through the original checker command.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def clean_env():
    env = os.environ.copy()
    # Git exposes the complete list; a hook may also select a worktree or index.
    keys = subprocess.check_output(['git', 'rev-parse', '--local-env-vars'], text=True).splitlines()
    for key in keys:
        env.pop(key, None)
    return env


def run(root: Path, command: list[str]) -> int:
    env = clean_env()
    def git(*args):
        return subprocess.check_output(['git', '-C', str(root), *args], env=env)
    # Capture the real invoking index before detaching repository environment.
    index_tree = subprocess.check_output(['git', '-C', str(root), 'write-tree']).decode().strip()
    root = Path(git('rev-parse', '--show-toplevel').decode().strip())
    with tempfile.TemporaryDirectory(prefix='sync-guardian-index-') as temporary:
        checkout = Path(temporary) / 'repo'
        subprocess.run(['git', 'clone', '--quiet', '--shared', '--no-checkout', str(root), str(checkout)], check=True, env=env)
        subprocess.run(['git', '-C', str(checkout), 'read-tree', index_tree], check=True, env=env)
        subprocess.run(['git', '-C', str(checkout), 'checkout-index', '--all', '--force'], check=True, env=env)
        env["PYTHONPATH"] = os.pathsep.join([str(checkout / "src"), str(checkout), env.get("PYTHONPATH", "")])
        argv = [sys.executable if item == 'python' and i == 0 else item for i, item in enumerate(command)]
        return subprocess.call(argv, cwd=checkout, env=env, shell=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if not command:
        parser.error('checker command is required')
    return run(args.root.resolve(), command)


if __name__ == '__main__':
    raise SystemExit(main())
