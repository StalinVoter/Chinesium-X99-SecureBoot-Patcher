from __future__ import annotations
import argparse
import json
from pathlib import Path

from .pipeline import inspect_rom, build_secureboot_rom, default_output
from .sessionlog import start_session_log, finish_session_log, install_exception_hook, log, log_json
from . import __version__


def main(argv=None) -> int:
    session_path = start_session_log(__version__, 'X99 Secureboot patcher CLI')
    install_exception_hook()
    log('SESSION', f'CLI session log: {session_path}')
    p = argparse.ArgumentParser(prog='X99-Secureboot-patcher', description='Inspect and update AMI X99 Secure Boot factory defaults using validated 2023 Secure Boot update payloads.')
    sub = p.add_subparsers(dest='cmd', required=True)
    i = sub.add_parser('inspect', help='inspect Secure Boot factory defaults')
    i.add_argument('rom', type=Path)
    b = sub.add_parser('patch', help='create an automatically planned Secure Boot 2023 ROM')
    b.add_argument('rom', type=Path)
    b.add_argument('-o','--output',type=Path)
    args=p.parse_args(argv)
    log_json('CLI', 'Parsed arguments', vars(args))
    try:
        if args.cmd=='inspect':
            report = inspect_rom(args.rom)
            print(json.dumps(report,indent=2))
            finish_session_log('CLI inspect completed')
            return 0
        out=args.output or default_output(args.rom)
        r=build_secureboot_rom(args.rom,out,lambda st,tx: print(f'[{st}] {tx}'))
        print(json.dumps(r.__dict__,indent=2,default=str))
        code = 0 if r.success else 1
        finish_session_log(f'CLI patch completed with exit code {code}')
        return code
    except BaseException as exc:
        log('CLI', f'CLI failed: {type(exc).__name__}: {exc}')
        finish_session_log('CLI failed')
        raise
