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
from doc_generator.models import AnalysisData
from doc_generator.validation import validate_analysis

logger = get_logger(__name__)


def _load_analysis_raw(path: Path) -> dict | None:
    """Load raw JSON dict from the analysis file path.

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


def _load_analysis(path: Path) -> AnalysisData:
    """Load and validate analysis.json, exiting on error (for human-readable mode)."""
    raw = _load_analysis_raw(path)
    if raw is None:
        sys.exit(1)

    try:
        return AnalysisData.model_validate(raw)
    except ValidationError as e:
        logger.error("Schema validation failed", error=str(e))
        sys.exit(1)


def _parse_analysis(raw: dict) -> AnalysisData | list[str]:
    """Parse raw dict into AnalysisData, returning error list on failure."""
    try:
        return AnalysisData.model_validate(raw)
    except ValidationError as e:
        errors = []
        for err in e.errors():
            loc = " → ".join(str(loc) for loc in err["loc"])
            errors.append(f"{loc}: {err['msg']}")
        return errors


def _resolve_output_path(
    data: AnalysisData, analysis_path: Path, output_arg: str | None
) -> Path:
    """Determine the final .docx output path."""
    if output_arg:
        return Path(output_arg).resolve()

    safe_name = (
        "".join(c for c in data.screen.name if c.isalnum() or c in (" ", "_", "-"))
        .strip()
        .replace(" ", "_")
    )
    return analysis_path.parent / f"{safe_name}.docx"


def _print_summary(analysis: AnalysisData):
    """Print a dry-run summary."""
    non_leaf = [c for c in analysis.components if not c.isLeaf]
    leaf = [c for c in analysis.components if c.isLeaf]
    total_children = sum(len(c.children) for c in non_leaf)
    total_interactions = sum(len(c.interactions) for c in non_leaf)
    screen_children = len(analysis.screen.topLevelChildren)
    screen_interactions = len(analysis.screen.interactions)

    logger.info("=" * 50)
    logger.info("  TLGP Doc Generator — Dry Run Summary")
    logger.info("=" * 50)
    logger.info("  Section prefix:     %s", analysis.sectionPrefix)
    logger.info("  Export dir:         %s", analysis.imageDir)
    logger.info("  Screen:             %s", analysis.screen.name)
    logger.info("")
    logger.info("  Components:         %d non-leaf, %d leaf", len(non_leaf), len(leaf))
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
    logger.info("  APIs:               %d", len(analysis.all_apis))
    logger.info("")

    # Count images
    image_count = 0
    missing_images = []
    for c in non_leaf:
        if c.imageFile:
            img = analysis.resolve_image(c.imageFile)
            image_count += 1
            if not img.exists():
                missing_images.append(str(img))
    for img_file in analysis.screen.imageFiles:
        img = analysis.resolve_image(img_file)
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
    table_count += len(non_leaf)  # info tables
    table_count += sum(1 for c in non_leaf if c.children)  # UI tables
    table_count += sum(1 for c in non_leaf if c.interactions)  # interaction tables
    table_count += 2  # screen info + screen general info
    if screen_children:
        table_count += 1
    if screen_interactions:
        table_count += 1
    for api in analysis.all_apis:
        if api.requestParams:
            table_count += 1
        if api.responseFields:
            table_count += 1
        table_count += sum(1 for s in api.subDtos if s.fields)

    logger.info("  Tables:             %d total", table_count)
    logger.info("=" * 50)


def _run_json_mode(
    analysis_path: Path,
    output_path: str | None,
    validate_only: bool,
) -> int:
    """Execute in JSON mode: all output is a single JSON object on stdout.

    Returns the process exit code (0 for success, 1 for failure).
    """
    sys.stdout.reconfigure(encoding="utf-8")
    raw = _load_analysis_raw(analysis_path)
    if raw is None:
        result = DocGenResult(valid=False, errors=[f"Failed to read {analysis_path}"])
        sys.stdout.write(result.model_dump_json())
        return 1

    parsed = _parse_analysis(raw)
    if isinstance(parsed, list):
        result = DocGenResult(valid=False, errors=parsed)
        sys.stdout.write(result.model_dump_json())
        return 1

    data: AnalysisData = parsed

    # Run validation
    vr = validate_analysis(data)

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

    out = _resolve_output_path(data, analysis_path, output_path)

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

    # Save analysis JSON alongside the docx
    analysis_json_dest = out.parent / "analysis.json"
    if analysis_path.resolve() != analysis_json_dest.resolve():
        shutil.copy2(analysis_path, analysis_json_dest)

    result = DocGenResult(
        **vr.model_dump(), output_path=str(out), tables=len(doc.tables)
    )
    sys.stdout.write(result.model_dump_json())
    return 0


def main():
    env = os.environ.get("TLGP_ENV", "dev")
    setup_logging(json_format=(env == "prod"))

    parser = argparse.ArgumentParser(
        prog="doc-generator",
        description="Generate TLGP screen spec .docx from analysis.json",
    )
    parser.add_argument(
        "analysis_json",
        nargs="?",
        help="Path to the analysis.json file",
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
        help="Validate analysis data without generating the .docx (implies --json)",
    )
    parser.add_argument(
        "--schema",
        action="store_true",
        help="Print the JSON schema of AnalysisData to stdout and exit immediately",
    )

    args = parser.parse_args()

    if args.schema:
        print(json.dumps(AnalysisData.model_json_schema(), indent=2, ensure_ascii=False))
        sys.exit(0)

    if args.analysis_json is None:
        parser.print_help()
        sys.exit(0)

    analysis_path = Path(args.analysis_json).resolve()

    # --validate-only implies --json
    if args.validate_only:
        args.json_mode = True

    # JSON mode: structured output for machine consumption
    if args.json_mode:
        exit_code = _run_json_mode(analysis_path, args.output, args.validate_only)
        sys.exit(exit_code)

    # Human-readable mode
    analysis = _load_analysis(analysis_path)

    # Enforce validation (was previously skipped in this code path)
    vr = validate_analysis(analysis)
    if vr.warnings:
        for w in vr.warnings:
            logger.warning(w)
    if not vr.valid:
        for err in vr.errors:
            logger.error(err)
        sys.exit(1)

    if args.dry_run:
        _print_summary(analysis)
        return

    # Build the document
    print("Building .docx...")
    doc = build_document(analysis)

    # Determine output path
    output_path = _resolve_output_path(analysis, analysis_path, args.output)
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

    # Copy analysis.json alongside the .docx for record-keeping
    analysis_dest = output_path.parent / "analysis.json"
    if analysis_path.resolve() != analysis_dest.resolve():
        shutil.copy2(analysis_path, analysis_dest)

    print(f"[OK] Saved to: {output_path}")


if __name__ == "__main__":
    main()
