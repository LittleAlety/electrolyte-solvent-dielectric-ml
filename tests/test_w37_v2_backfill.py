# -*- coding: utf-8 -*-
"""W37-C 的守卫测试：重建产物必须与已发布稿逐字节相等，拼接锚点必须唯一。

这些断言把「装配源 = 交付字节」钉死。任何人再手工改已发布稿（或改装配源却
不同步另一侧），下面的第一个测试就会红。
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "probes"))

from w37_v2_backfill import (  # noqa: E402
    PAPER,
    SHIPPED_DRAFT,
    SPLICE_JSON,
    drift_blocks,
    rebuild_to_temp,
    read_text,
    strip_rules,
)

SHIPPED_SHA256 = "dfb3b282f8ccf76653d244a6a2c618d92a6e12003d012b81cca9f08dc9c6e78e"


def test_the_shipped_draft_bytes_are_pinned() -> None:
    digest = hashlib.sha256(SHIPPED_DRAFT.read_bytes()).hexdigest()
    assert digest == SHIPPED_SHA256


def test_a_rebuild_reproduces_the_shipped_draft_byte_for_byte() -> None:
    shipped = read_text(SHIPPED_DRAFT)
    rebuilt = rebuild_to_temp()
    assert drift_blocks(shipped, rebuilt) == []
    assert rebuilt == shipped


def test_rebuilding_twice_is_idempotent() -> None:
    first = rebuild_to_temp()
    second = rebuild_to_temp()
    assert first == second


def test_the_splice_file_declares_its_schema_and_is_lf() -> None:
    payload = json.loads(read_text(SPLICE_JSON))
    assert payload["schema"] == "paper_v2_splices@1"
    assert payload["splices"], "拼接清单不该为空"
    assert b"\r\n" not in SPLICE_JSON.read_bytes()
    for item in payload["splices"]:
        assert item["mode"] in ("insert_between", "replace")
        if item["mode"] == "insert_between":
            assert item["before"] + "\n" + item["after"]
        else:
            assert item["find"]
        assert "source" in item or "content" in item
        if "source" in item:
            assert (REPOSITORY_ROOT / item["source"]).is_file()


def test_every_splice_anchor_exists_in_the_assembled_text_exactly_once() -> None:
    """锚点唯一性：把清单里的每一处照重建器的方式，在装配产物上数一遍。

    重建器本身在命中数 != 1 时会直接退出，所以这一条是和它互相独立的复算。
    """

    payload = json.loads(read_text(SPLICE_JSON))
    spliced = rebuild_to_temp(use_splices=True)
    plain = rebuild_to_temp(use_splices=False)
    assert spliced != plain, "拼接清单没有产生任何效果"
    for item in payload["splices"]:
        needle = (item["before"] + "\n" + item["after"]) if item["mode"] == "insert_between" else item["find"]
        assert plain.count(needle) == 1, item["id"]


def test_source_files_end_with_lf_and_have_no_bom() -> None:
    for name in ("_v2_body_b.md", "_v2_appendix.md", "_v2_concl.md", "_v2_disc_extra.md"):
        raw = (PAPER / name).read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf"), name
        assert b"\r\n" not in raw, name
        assert raw.endswith(b"\n"), name


def test_strip_rules_matches_the_builder_semantics() -> None:
    assert strip_rules("a\n\n---\n\n") == "a"
    assert strip_rules("\n\na\n") == "a"
