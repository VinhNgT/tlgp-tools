"""Tests for CLI argument parsing and integration."""

import json
from unittest.mock import patch

import pytest
from doc_generator.cli import main


class TestCliHelp:
    def test_no_args_prints_help(self, capsys):
        with patch("sys.argv", ["doc-gen"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0
        captured = capsys.readouterr()
        assert "analysis.json" in captured.out

    def test_help_flag(self, capsys):
        with patch("sys.argv", ["doc-gen", "--help"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0


class TestCliValidation:
    def test_nonexistent_file(self, capsys):
        with patch("sys.argv", ["doc-gen", "/nonexistent/analysis.json"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 1
        captured = capsys.readouterr()
        assert "File not found" in captured.out or "File not found" in captured.err

    def test_invalid_json(self, tmp_path, capsys):
        bad_json = tmp_path / "bad.json"
        bad_json.write_text("not json at all", encoding="utf-8")
        with patch("sys.argv", ["doc-gen", str(bad_json)]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 1
        captured = capsys.readouterr()
        assert "Invalid JSON" in captured.out or "Invalid JSON" in captured.err

    def test_invalid_schema(self, tmp_path, capsys):
        bad_schema = tmp_path / "bad_schema.json"
        bad_schema.write_text('{"foo": "bar"}', encoding="utf-8")
        with patch("sys.argv", ["doc-gen", str(bad_schema)]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 1
        captured = capsys.readouterr()
        assert (
            "Schema validation failed" in captured.out
            or "Schema validation failed" in captured.err
        )


class TestCliDryRun:
    def test_dry_run_prints_summary(self, tmp_path, capsys):
        analysis = {
            "sectionPrefix": "1.1",
            "exportDir": str(tmp_path),
            "screen": {"name": "Test"},
            "components": [],
        }
        json_path = tmp_path / "analysis.json"
        json_path.write_text(json.dumps(analysis), encoding="utf-8")

        with patch("sys.argv", ["doc-gen", str(json_path), "--dry-run"]):
            main()

        captured = capsys.readouterr()
        assert "Dry Run Summary" in captured.out
        assert "Test" in captured.out
        assert "Components:" in captured.out


class TestCliGeneration:
    def test_generates_docx(self, tmp_path):
        analysis = {
            "sectionPrefix": "1.1",
            "exportDir": str(tmp_path),
            "screen": {"name": "My Screen", "description": "D"},
            "components": [],
        }
        json_path = tmp_path / "analysis.json"
        json_path.write_text(json.dumps(analysis), encoding="utf-8")

        output_path = tmp_path / "output.docx"
        with patch("sys.argv", ["doc-gen", str(json_path), "-o", str(output_path)]):
            main()

        assert output_path.exists()
        assert output_path.stat().st_size > 0

    def test_default_output_name(self, tmp_path):
        analysis = {
            "sectionPrefix": "1.1",
            "exportDir": str(tmp_path),
            "screen": {"name": "Product Detail"},
        }
        json_path = tmp_path / "analysis.json"
        json_path.write_text(json.dumps(analysis), encoding="utf-8")

        with patch("sys.argv", ["doc-gen", str(json_path)]):
            main()

        expected = tmp_path / "Product_Detail.docx"
        assert expected.exists()


class TestCliImageWarnings:
    def test_dry_run_shows_missing_images(self, tmp_path, capsys):
        analysis = {
            "sectionPrefix": "1.1",
            "exportDir": str(tmp_path),
            "screen": {"name": "T", "imageFiles": ["missing.png"]},
            "components": [
                {"id": 1, "label": "A", "imageFile": "also_missing.png"},
            ],
        }
        json_path = tmp_path / "analysis.json"
        json_path.write_text(json.dumps(analysis), encoding="utf-8")

        with patch("sys.argv", ["doc-gen", str(json_path), "--dry-run"]):
            main()

        captured = capsys.readouterr()
        assert "Missing images" in captured.out
