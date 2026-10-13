"""Offline JSONL replay: strict inputs, audit log, public outputs, SHA-256 manifest."""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys

from competition.interfaces.validate import loads
from .core import Config, Mission
from .synthetic import synthetic_config, demo_traces


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replay(input_path, config, session_id, clock_id, output_dir):
    """Refuse overwrite. A parser rejection is logged and latches a stop fault."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=False)
    machine = Mission(session_id, clock_id, config)
    count = rejected = 0
    with Path(input_path).open(encoding="utf-8") as source, \
            (output_dir / "audit.jsonl").open("w", encoding="utf-8") as audit, \
            (output_dir / "public.jsonl").open("w", encoding="utf-8") as public:
        for line_number, line in enumerate(source, 1):
            if not line.strip():
                continue
            parse_error = None
            try:
                record = loads(line)
                received_ns = record.get("stamp_ns") if isinstance(record, dict) else machine.now_ns
                if isinstance(record, dict) and set(record) == {"received_ns", "record"}:
                    received_ns, record = record["received_ns"], record["record"]
            except (ValueError, TypeError) as exc:
                record, received_ns, parse_error = {}, machine.now_ns, str(exc)
            out = machine.step(record, received_ns)
            out.update(input_line=line_number, input_sha256=hashlib.sha256(line.encode()).hexdigest(),
                       parse_error=parse_error)
            audit.write(json.dumps(out, ensure_ascii=False, allow_nan=False) + "\n")
            for key in ("state_event", "motion_request"):
                public.write(json.dumps(out[key], ensure_ascii=False, allow_nan=False) + "\n")
            count += 1
            rejected += not out["accepted"]
    summary = machine.snapshot()
    summary.update(input_records=count, rejected_records=rejected, autonomous_success=False,
                   verdict="synthetic_logic_only" if config.evidence_role == "synthetic" else "offline_evidence_only",
                   input_sha256=digest(Path(input_path)), public_sha256=digest(output_dir / "public.jsonl"),
                   audit_sha256=digest(output_dir / "audit.jsonl"),
                   code_sha256={p.name: digest(p) for p in sorted(Path(__file__).parent.glob("*.py"))})
    write_json(output_dir / "summary.json", summary)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run")
    run.add_argument("input", type=Path)
    run.add_argument("--config", required=True, type=Path)
    run.add_argument("--session", required=True)
    run.add_argument("--clock", required=True)
    run.add_argument("--out", required=True, type=Path)
    demo = commands.add_parser("demo")
    demo.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.command == "run":
        config = Config(**loads(args.config.read_text(encoding="utf-8")))
        summary = replay(args.input, config, args.session, args.clock, args.out)
        print(json.dumps({k: summary[k] for k in ("state", "lap_completed", "input_records", "rejected_records", "verdict")}))
        return 2 if summary["fault_reason"] else 0
    args.out.mkdir(parents=True, exist_ok=False)
    config = synthetic_config()
    write_json(args.out / "config.json", asdict(config))
    index = {}
    for name, trace in demo_traces().items():
        input_path = args.out / (name + ".input.jsonl")
        input_path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in trace.rows), encoding="utf-8")
        summary = replay(input_path, config, trace.session, trace.clock, args.out / name)
        index[name] = {k: summary[k] for k in ("state", "lap_completed", "input_records", "rejected_records", "fault_reason")}
    write_json(args.out / "index.json", index)
    print(json.dumps(index, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
