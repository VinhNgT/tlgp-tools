"""CLI entry point for the TLGP doc generator."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

from pydantic import ValidationError
from tlgp_contracts import DocGenResult
from tlgp_logger import get_logger, setup_logging

from doc_generator.doc_builder import build_document
from doc_generator.models import ScreenSpec
from doc_generator.validation import validate_spec

logger = get_logger(__name__)


def _load_spec_raw(path: Path) -> dict | None:
    """Load raw JSON dict from the spec file path.

    Returns the parsed dict on success. On failure, returns None after
    logging the error and (in non-JSON mode) exiting.
    """
    if not path.exists():
        logger.error("File not found: %s", path)
        return None

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        logger.error("Invalid JSON", error=str(e))
        return None


def _load_spec(path: Path) -> ScreenSpec:
    """Load and validate spec.json, exiting on error (for human-readable mode)."""
    raw = _load_spec_raw(path)
    if raw is None:
        sys.exit(1)

    try:
        return ScreenSpec.model_validate(raw)
    except ValidationError as e:
        logger.error("Schema validation failed", error=str(e))
        sys.exit(1)


def _parse_spec(raw: dict) -> ScreenSpec | list[str]:
    """Parse raw dict into ScreenSpec, returning error list on failure."""
    try:
        return ScreenSpec.model_validate(raw)
    except ValidationError as e:
        errors = []
        for err in e.errors():
            loc = " → ".join(str(loc) for loc in err["loc"])
            errors.append(f"{loc}: {err['msg']}")
        return errors


def _resolve_output_path(
    data: ScreenSpec, spec_path: Path, output_arg: str | None
) -> Path:
    """Determine the final .docx output path."""
    if output_arg:
        return Path(output_arg).resolve()

    safe_name = (
        "".join(c for c in data.screen.label if c.isalnum() or c in (" ", "_", "-"))
        .strip()
        .replace(" ", "_")
    )
    return spec_path.parent / f"{safe_name}.docx"


def _print_summary(spec: ScreenSpec):
    """Print a dry-run summary."""
    sub_components = [n for n in spec.nodes if n.id != spec.rootId and len(n.childrenIds) > 0]
    total_children = sum(len(c.childrenIds) for c in sub_components)
    total_interactions = sum(len(c.interactions) for c in sub_components)
    screen_children = len(spec.screen.childrenIds)
    screen_interactions = len(spec.screen.interactions)

    logger.info("=" * 50)
    logger.info("  TLGP Doc Generator — Dry Run Summary")
    logger.info("=" * 50)
    logger.info("  Section prefix:     %s", spec.sectionPrefix)
    logger.info("  Export dir:         %s", spec.imageDir)
    logger.info("  Screen:             %s", spec.screen.label)
    logger.info("")
    logger.info("  Components:         %d sub-components", len(sub_components))
    logger.info(
        "  UI elements:        %d (components) + %d (screen)",
        total_children,
        screen_children,
    )
    logger.info(
        "  Interactions:       %d (components) + %d (screen)",
        total_interactions,
        screen_interactions,
    )
    logger.info("  APIs:               %d", len(spec.all_apis))
    logger.info("")

    # Count images
    image_count = 0
    missing_images = []
    for c in sub_components:
        for img_file in c.imageFiles:
            if img_file:
                img = spec.resolve_image(img_file)
                image_count += 1
                if not img.exists():
                    missing_images.append(str(img))
    for img_file in spec.screen.imageFiles:
        img = spec.resolve_image(img_file)
        image_count += 1
        if not img.exists():
            missing_images.append(str(img))

    logger.info("  Images:             %d referenced", image_count)
    if missing_images:
        logger.info("  [WARN] Missing images:  %d", len(missing_images))
        for m in missing_images:
            logger.info("     - %s", m)
    else:
        logger.info("  [OK] All images found")

    # Estimate tables
    table_count = 0
    table_count += len(sub_components)  # info tables
    table_count += sum(1 for c in sub_components if c.childrenIds)  # UI tables
    table_count += sum(1 for c in sub_components if c.interactions)  # interaction tables
    table_count += 2  # screen info + screen general info
    if screen_children:
        table_count += 1
    if screen_interactions:
        table_count += 1
    for api in spec.all_apis:
        for payload in api.request:
            if payload.fields:
                table_count += 1
        for payload in api.response:
            if payload.fields:
                table_count += 1

    logger.info("  Tables:             %d total", table_count)
    logger.info("=" * 50)


def _run_json_mode(
    spec_path: Path,
    output_path: str | None,
    validate_only: bool,
    skip_image_validation: bool = False,
) -> int:
    """Execute in JSON mode: all output is a single JSON object on stdout.

    Returns the process exit code (0 for success, 1 for failure).
    """
    sys.stdout.reconfigure(encoding="utf-8")
    raw = _load_spec_raw(spec_path)
    if raw is None:
        result = DocGenResult(valid=False, errors=[f"Failed to read {spec_path}"])
        sys.stdout.write(result.model_dump_json())
        return 1

    parsed = _parse_spec(raw)
    if isinstance(parsed, list):
        result = DocGenResult(valid=False, errors=parsed)
        sys.stdout.write(result.model_dump_json())
        return 1

    data: ScreenSpec = parsed

    # Run validation
    vr = validate_spec(data, skip_image_validation=skip_image_validation)

    if not vr.valid:
        result = DocGenResult(**vr.model_dump())
        sys.stdout.write(result.model_dump_json())
        return 1

    if validate_only:
        result = DocGenResult(**vr.model_dump())
        sys.stdout.write(result.model_dump_json())
        return 0

    # Build document
    doc = build_document(data)

    out = _resolve_output_path(data, spec_path, output_path)

    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        doc.save(str(out))
    except PermissionError as e:
        result = DocGenResult(**vr.model_dump())
        result.valid = False
        result.errors.append(
            f"Permission denied: Could not save to {out}. Please ensure the file is closed and not locked by another application (e.g. Microsoft Word). Detail: {e}"
        )
        sys.stdout.write(result.model_dump_json())
        return 1

    # Save spec.json alongside the docx
    spec_json_dest = out.parent / "spec.json"
    if spec_path.resolve() != spec_json_dest.resolve():
        shutil.copy2(spec_path, spec_json_dest)

    result = DocGenResult(
        **vr.model_dump(), output_path=str(out), tables=len(doc.tables)
    )
    sys.stdout.write(result.model_dump_json())
    return 0


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    env = os.environ.get("TLGP_ENV", "dev")
    setup_logging(json_format=(env == "prod"))

    parser = argparse.ArgumentParser(
        prog="doc-generator",
        description="Generate TLGP screen spec .docx from spec.json",
    )
    parser.add_argument(
        "spec_json",
        nargs="?",
        help="Path to the spec.json file",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Output .docx file path (default: <screen_name>.docx next to the JSON)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print summary without generating the .docx",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_mode",
        help="Output a single JSON result object to stdout (machine-readable mode)",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate spec data without generating the .docx (implies --json)",
    )
    parser.add_argument(
        "--schema",
        action="store_true",
        help="Print the JSON schema of ScreenSpec to stdout and exit immediately",
    )
    parser.add_argument(
        "--skip-image-validation",
        action="store_true",
        help="Skip image existence and path checks",
    )

    args = parser.parse_args()

    if args.schema:
        print(
            json.dumps(ScreenSpec.model_json_schema(), indent=2, ensure_ascii=False)
        )
        sys.exit(0)

    if args.spec_json is None:
        parser.print_help()
        sys.exit(0)

    spec_path = Path(args.spec_json).resolve()

    # --validate-only implies --json
    if args.validate_only:
        args.json_mode = True

    # JSON mode: structured output for machine consumption
    if args.json_mode:
        exit_code = _run_json_mode(
            spec_path,
            args.output,
            args.validate_only,
            skip_image_validation=args.skip_image_validation,
        )
        sys.exit(exit_code)

    # Human-readable mode
    spec = _load_spec(spec_path)

    # Enforce validation
    vr = validate_spec(spec, skip_image_validation=args.skip_image_validation)
    if vr.warnings:
        for w in vr.warnings:
            logger.warning(w)
    if not vr.valid:
        for err in vr.errors:
            logger.error(err)
        sys.exit(1)

    if args.dry_run:
        _print_summary(spec)
        return

    # Build the document
    print("Building .docx...")
    doc = build_document(spec)

    # Determine output path
    output_path = _resolve_output_path(spec, spec_path, args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        doc.save(str(output_path))
    except PermissionError as e:
        logger.error(
            "Permission denied: Could not save to %s. Please ensure the file is closed and not locked by another application (e.g. Microsoft Word).",
            output_path,
            error=str(e),
        )
        sys.exit(1)

    # Copy spec.json alongside the .docx for record-keeping
    spec_dest = output_path.parent / "spec.json"
    if spec_path.resolve() != spec_dest.resolve():
        shutil.copy2(spec_path, spec_dest)

    print(f"[OK] Saved to: {output_path}")


if __name__ == "__main__":
    main()