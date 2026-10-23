"""Entrypoint: venv/bin/python -m weekly_review.run --week 2026-W31 --stage all

Stages: pull -> join -> compute -> publish(stub). READ-ONLY against Meta
(GET requests only). Tokens are redacted from all output.
"""

from __future__ import annotations

import argparse
import os
import sys

from . import compute, join, publish, pull
from .common import load_config, load_env, redact, week_window
from .meta_client import MetaClient

STAGES = ["pull", "join", "compute", "publish"]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="weekly_review",
                                 description="Weekly Meta ads review (deterministic core)")
    ap.add_argument("--week", required=True, help="ISO week label, e.g. 2026-W31")
    ap.add_argument("--stage", default="all", choices=STAGES + ["all"])
    ap.add_argument("--force", action="store_true",
                    help="re-pull even if raw caches exist")
    args = ap.parse_args(argv)

    cfg = load_config()
    since, until = week_window(args.week)
    stages = STAGES if args.stage == "all" else [args.stage]
    print(f"weekly_review {args.week} ({since}..{until}) stages={stages}")

    try:
        for stage in stages:
            if stage == "pull":
                load_env(cfg)
                client = MetaClient(cfg,
                                    os.getenv("META_ACCESS_TOKEN", ""),
                                    os.getenv("META_AD_ACCOUNT_ID", ""))
                pull.run(cfg, client, args.week, force=args.force)
            elif stage == "join":
                join.run(cfg, args.week)
            elif stage == "compute":
                compute.run(cfg, args.week)
            elif stage == "publish":
                publish.run(cfg, args.week)
    except Exception as e:  # redact any token before the traceback surfaces
        print(f"ERROR in stage run: {redact(e)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
