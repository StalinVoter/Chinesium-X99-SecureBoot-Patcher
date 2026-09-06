from __future__ import annotations
import argparse
import json
from pathlib import Path

from .pipeline import inspect_rom, build_secureboot_rom, default_output


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog='X99-Secureboot-patcher', description='Inspect and update AMI X99 Secure Boot factory defaults using validated 2023 Secure Boot update payloads.')
    sub = p.add_subparsers(dest='cmd', required=True)
    i = sub.add_parser('inspect', help='inspect Secure Boot factory defaults')
    i.add_argument('rom', type=Path)
    b = sub.add_parser('patch', help='create an automatically planned Secure Boot 2023 ROM')
    b.add_argument('rom', type=Path)
    b.add_argument('-o','--output',type=Path)
    args=p.parse_args(argv)
    if args.cmd=='inspect':
        print(json.dumps(inspect_rom(args.rom),indent=2)); return 0
    out=args.output or default_output(args.rom)
    r=build_secureboot_rom(args.rom,out,lambda st,tx: print(f'[{st}] {tx}'))
    print(json.dumps(r.__dict__,indent=2,default=str))
    return 0 if r.success else 1
