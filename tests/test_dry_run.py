"""Tests for dry-run output rendering and the DRY_RUN config flag."""
import os
import importlib

import main
from src.config import Config


def test_write_dry_run_output_creates_md_and_html(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    content = "# Heading\n\nSome **digest** body with a [link](https://example.com)."
    md_path, html_path = main.write_dry_run_output(content)

    assert md_path.exists() and html_path.exists()
    assert md_path.name == "digest.md" and html_path.name == "digest.html"
    assert md_path.read_text(encoding="utf-8") == content
    html = html_path.read_text(encoding="utf-8")
    # Markdown was rendered into the email HTML shell.
    assert "<html>" in html.lower()
    assert "AI News Digest" in html
    assert "digest" in html


def test_dry_run_config_flag(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "true")
    assert Config().dry_run is True
    monkeypatch.setenv("DRY_RUN", "false")
    assert Config().dry_run is False
    monkeypatch.delenv("DRY_RUN", raising=False)
    assert Config().dry_run is False
