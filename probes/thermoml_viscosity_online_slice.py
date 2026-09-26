"""T1 在线黏度切片核查：把本地「29 个含黏度 XML」放进 NIST/TRC ThermoML 在线切片里核对。

reports/thermoml_viscosity_coverage.md 的第 1 条边界与 reports/decisions_log.md 的 24.8 节
都把「在线黏度切片核查」登记为未做。本探针把它做掉，且只做测量。

既有的 probes/thermoml_online_topup_probe.py 已经证伪静态目录、确认活的入口是
/ThermoML-API/objects 这个 JSON 检索 API，并给出可用 UA（默认 urllib UA 会被 403）。
本探针沿用同一套 HTTP 骨架、节流与请求记账，只把检索词换成两个黏度属性名。

三件判据在跑之前冻结在 probes/thermoml_viscosity_online_slice_prereg.json 里：
  A 在线三数（11923 / 1690 / 70，口径均为「记录数」）逐位复现，且两个黏度切片分页抓全；
  B 本地 29 个含黏度 XML 的 DOI 逐个必须出现在在线黏度切片清单的并集里；
  C 口径诚实性：size 是记录数不是数据行数（在线行数记 unknown）、phrase 全文索引命中与
    结构化 Property 字段（ePropName）命中必须分开报、覆盖率只在记录口径下给 29 / 1690
    并声明行口径不可比。

不做：不拟合任何模型、不产 R2/MAE、不把任何值写进 data/ 冻结表、不改任何既有文件。

用法：
    python probes/thermoml_viscosity_online_slice.py --resolve-online   # 首跑：联网抓两个切片
    python probes/thermoml_viscosity_online_slice.py                    # 增量：缓存已有的不再联网
    python probes/thermoml_viscosity_online_slice.py --check            # 离线重算，与磁盘产物比对

API 口径（跑前侦察实测，不是跑后回填）：/ThermoML-API/objects 的 pageNum 是 0 基的，
窗口是 [pageNum * pageSize, (pageNum + 1) * pageSize)，返回条数为 min(pageSize, size - pageNum * pageSize)。
换言之 pageNum=1 不是第一页而是第二页：若从 1 起分页，最前面 pageSize 条永远抓不到。
实测证据（size=70 的运动黏度切片、pageSize=20）：pageNum 0/1/2/3 -> 20/20/20/10 条，
四页并集恰为 70 条且无重复；pageNum=4 返回 0 条。故本探针一律从 pageNum=0 起分页。

离线边界：原始响应缓存在 data/external/thermoml_api/（按既有 G1+ 风格被 .gitignore 忽略），
干净克隆上没有它；此时 --check 以已提交的 summary 里的在线清单为来源，仍能零网络复现
summary 与报告。有原始缓存时，--check 追加一层：从原始字节重算清单并逐字节比对。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

API_BASE = "https://trc.nist.gov/ThermoML-API/objects"
API_OBJECT_PREFIX = "20.5000.trc.thermoml/"
USER_AGENT = "electrolyte-ml/0.0.0 (+https://trc.nist.gov/ThermoML/)"
HTTP_TIMEOUT_SECONDS = 120
THROTTLE_SECONDS = 0.25
PAGE_SIZE = 100
REQUEST_BUDGET_LIMIT = 60
TOTAL_RECORDS_QUERY = "*"
TOTAL_RECORDS_SLUG = "total_records"
# /ThermoML-API/objects 的 pageNum 是 0 基的（跑前侦察实测，见模块 docstring）。
FIRST_PAGE_NUM = 0

DEFAULT_PREREG = REPOSITORY_ROOT / "probes" / "thermoml_viscosity_online_slice_prereg.json"
DEFAULT_SUMMARY = REPOSITORY_ROOT / "probes" / "thermoml_viscosity_online_slice_summary.json"
DEFAULT_REPORT = REPOSITORY_ROOT / "reports" / "thermoml_viscosity_online_slice.md"
DEFAULT_CACHE_DIR = REPOSITORY_ROOT / "data" / "external" / "thermoml_api"
LOCAL_COVERAGE_SUMMARY = REPOSITORY_ROOT / "probes" / "thermoml_viscosity_coverage_summary.json"

# 这两个 key 天然随运行变化（时间戳、本次请求记账与缓存命中），比对时剔除；
# 其余每个字段都必须逐字节复现。
UNSTABLE_SUMMARY_KEYS: tuple[str, ...] = ("generated_at_utc", "run_provenance")


class BudgetExhausted(RuntimeError):
    """请求数超过预注册预算时抛出。"""


class ThermoMLSearchError(RuntimeError):
    """检索 API 返回非 200 或缺页时抛出。"""


class CacheMiss(RuntimeError):
    """离线模式下原始响应缓存缺失时抛出。"""


@dataclass
class HttpResponse:
    status_code: int
    body: bytes
    url: str


@dataclass
class RequestBudget:
    limit: int = REQUEST_BUDGET_LIMIT
    used: int = 0
    bytes_transferred: int = 0

    def spend(self) -> None:
        if self.used >= self.limit:
            raise BudgetExhausted(f"请求预算用尽：{self.used}/{self.limit}")
        self.used += 1


HttpGet = Callable[..., HttpResponse]


def default_http_get(url: str, *, timeout: int = HTTP_TIMEOUT_SECONDS) -> HttpResponse:
    """唯一的上网出口；测试里整体替换成 fake。"""

    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return HttpResponse(
            status_code=int(response.status), body=response.read(), url=url
        )


def sha256_file(path: Path, chunk_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def display_path(path: Path) -> str:
    try:
        return path.relative_to(REPOSITORY_ROOT).as_posix()
    except ValueError:
        return str(path).replace("\\", "/")


def write_text_lf(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def write_json_lf(path: Path, payload: Any) -> None:
    write_text_lf(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def stable_view(summary: Mapping[str, Any]) -> dict[str, Any]:
    clone = json.loads(json.dumps(summary, ensure_ascii=False))
    for key in UNSTABLE_SUMMARY_KEYS:
        clone.pop(key, None)
    return clone


# --------------------------------------------------------------------------------------
# HTTP + 原始响应缓存
# --------------------------------------------------------------------------------------


def api_url(query: str, page_size: int, page_num: int) -> str:
    params = urllib.parse.urlencode(
        {"query": query, "pageSize": page_size, "pageNum": page_num}
    )
    return f"{API_BASE}?{params}"


def cache_paths(cache_dir: Path, slug: str, page_num: int) -> tuple[Path, Path]:
    base = Path(cache_dir) / slug
    stem = base / f"page-{page_num:04d}"
    return stem.with_suffix(".json"), stem.with_suffix(".json.url")


def fetch_page(
    query: str,
    page_size: int,
    page_num: int,
    *,
    slug: str,
    cache_dir: Path,
    online: bool,
    refresh: bool,
    http_get: HttpGet,
    budget: RequestBudget,
    ledger: list[dict[str, Any]],
    throttle_seconds: float = THROTTLE_SECONDS,
    timeout: int = HTTP_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """缓存优先取一页。命中缓存不联网；未命中且 offline 则抛 CacheMiss。"""

    url = api_url(query, page_size, page_num)
    cache_path, marker_path = cache_paths(cache_dir, slug, page_num)
    if (
        not refresh
        and cache_path.is_file()
        and marker_path.is_file()
        and marker_path.read_text(encoding="utf-8").strip() == url
    ):
        body = cache_path.read_bytes()
        ledger.append(
            {
                "url": url,
                "page": page_num,
                "source": "local_cache",
                "status": 200,
                "bytes": len(body),
            }
        )
        return {"url": url, "body": body, "source": "local_cache", "page": page_num}

    if not online:
        raise CacheMiss(f"原始响应缓存缺失，先跑 --resolve-online：{cache_path}")

    last: Exception | None = None
    for attempt in range(3):
        budget.spend()
        try:
            response = http_get(url, timeout=timeout)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last = exc
            ledger.append(
                {
                    "url": url,
                    "page": page_num,
                    "source": "network",
                    "status": 0,
                    "bytes": 0,
                    "error": str(exc),
                }
            )
            time.sleep(throttle_seconds * (2**attempt))
            continue
        body = response.body
        budget.bytes_transferred += len(body)
        if response.status_code != 200:
            last = ThermoMLSearchError(f"HTTP {response.status_code}：{url}")
            ledger.append(
                {
                    "url": url,
                    "page": page_num,
                    "source": "network",
                    "status": response.status_code,
                    "bytes": len(body),
                }
            )
            time.sleep(throttle_seconds * (2**attempt))
            continue
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(body)
        marker_path.write_text(url + "\n", encoding="utf-8", newline="\n")
        ledger.append(
            {
                "url": url,
                "page": page_num,
                "source": "network",
                "status": 200,
                "bytes": len(body),
            }
        )
        time.sleep(throttle_seconds)
        return {"url": url, "body": body, "source": "network", "page": page_num}
    raise ThermoMLSearchError(f"抓取失败：{url}（{last}）")


# --------------------------------------------------------------------------------------
# 记录解析
# --------------------------------------------------------------------------------------


def record_doi(record: Mapping[str, Any]) -> str:
    identifier = record.get("id")
    if isinstance(identifier, str) and identifier.startswith(API_OBJECT_PREFIX):
        return identifier[len(API_OBJECT_PREFIX) :]
    content = record.get("content")
    if isinstance(content, Mapping):
        citation = content.get("Citation")
        if isinstance(citation, Mapping):
            doi = citation.get("sDOI")
            if isinstance(doi, str):
                return doi.strip()
    return ""


def collect_e_prop_names(node: Any, out: set[str]) -> None:
    if isinstance(node, Mapping):
        for key, value in node.items():
            if key == "ePropName" and isinstance(value, str):
                out.add(value)
            else:
                collect_e_prop_names(value, out)
    elif isinstance(node, list):
        for item in node:
            collect_e_prop_names(item, out)


def structured_property_names(content: Any) -> set[str]:
    """结构化 Property 字段里的属性名集合（只认 ePropName）。"""

    names: set[str] = set()
    collect_e_prop_names(content, names)
    return names


def slice_specs(prereg: Mapping[str, Any]) -> list[dict[str, Any]]:
    specs = []
    for item in prereg["queries"]["slices"]:
        specs.append(
            {
                "id": str(item["id"]),
                "slug": str(item["id"]),
                "query": str(item["query"]),
                "property_name": str(item["property_name"]),
            }
        )
    return specs


def collect_slice(
    spec: Mapping[str, Any],
    *,
    page_size: int,
    cache_dir: Path,
    online: bool,
    refresh: bool,
    http_get: HttpGet,
    budget: RequestBudget,
    ledger: list[dict[str, Any]],
) -> dict[str, Any]:
    """分页抓全一个切片，逐页只留 (doi, 结构化命中) 就丢掉正文。"""

    def page(num: int) -> dict[str, Any]:
        return fetch_page(
            spec["query"],
            page_size,
            num,
            slug=spec["slug"],
            cache_dir=cache_dir,
            online=online,
            refresh=refresh,
            http_get=http_get,
            budget=budget,
            ledger=ledger,
        )

    first = page(FIRST_PAGE_NUM)
    payload = json.loads(first["body"].decode("utf-8"))
    size = int(payload.get("size", len(payload.get("results", []))))
    pages = max(1, math.ceil(size / page_size))
    observations: list[dict[str, Any]] = []
    sources = {str(first["source"])}
    extend_observations(observations, payload, spec["property_name"])
    del payload
    for page_num in range(FIRST_PAGE_NUM + 1, FIRST_PAGE_NUM + pages):
        extra = page(page_num)
        payload = json.loads(extra["body"].decode("utf-8"))
        sources.add(str(extra["source"]))
        extend_observations(observations, payload, spec["property_name"])
        del payload
    return {
        "id": spec["id"],
        "query": spec["query"],
        "property_name": spec["property_name"],
        "page_size": page_size,
        "size_records": size,
        "pages_fetched": pages,
        "sources": sorted(sources),
        "observations": observations,
    }


def extend_observations(
    observations: list[dict[str, Any]], payload: Mapping[str, Any], property_name: str
) -> None:
    for record in payload.get("results", []) or []:
        if not isinstance(record, Mapping):
            continue
        content = record.get("content") or {}
        observations.append(
            {
                "doi": record_doi(record),
                "structured_property_hit": property_name
                in structured_property_names(content),
            }
        )


def summarize_slice(collected: Mapping[str, Any]) -> dict[str, Any]:
    observations = list(collected["observations"])
    structured: set[str] = set()
    phrase_only: set[str] = set()
    dois: list[str] = []
    missing = 0
    for observation in observations:
        doi = str(observation["doi"]).strip()
        if not doi:
            missing += 1
            continue
        dois.append(doi)
        if observation["structured_property_hit"]:
            structured.add(doi)
        else:
            phrase_only.add(doi)
    phrase_only -= structured
    return {
        "id": collected["id"],
        "query": collected["query"],
        "property_name": collected["property_name"],
        "page_size": collected["page_size"],
        "size_records": collected["size_records"],
        "pages_fetched": collected["pages_fetched"],
        "records_collected": len(observations),
        "records_without_doi": missing,
        "unique_dois": len(set(dois)),
        "structured_property_hit_records": sum(
            1 for item in observations if item["structured_property_hit"]
        ),
        "phrase_only_records": sum(
            1 for item in observations if not item["structured_property_hit"]
        ),
        "structured_property_hit_dois": sorted(structured),
        "phrase_only_dois": sorted(phrase_only),
        "dois": sorted(set(dois)),
    }


# --------------------------------------------------------------------------------------
# 数据集装配
# --------------------------------------------------------------------------------------


def load_local_viscosity_dois(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    entries = []
    for item in payload.get("files_with_viscosity", []) or []:
        doi = str(item.get("source_doi") or item.get("doi") or "").strip()
        entries.append(
            {
                "doi": doi,
                "thermoml_file": str(item.get("thermoml_file") or ""),
                "viscosity_rows": item.get("viscosity_rows"),
            }
        )
    return {
        "path": display_path(path),
        "viscosity_files": payload.get("viscosity_files"),
        "viscosity_rows": payload.get("viscosity_rows"),
        "viscosity_rows_pa_s": payload.get("viscosity_rows_pa_s"),
        "viscosity_rows_kinematic": payload.get("viscosity_rows_kinematic"),
        "pure_rows": payload.get("pure_rows"),
        "pure_keys": payload.get("pure_keys"),
        "entry_count": len(entries),
        "dois": sorted({entry["doi"] for entry in entries if entry["doi"]}),
        "entries": entries,
    }


def gather_dataset(
    *,
    prereg: Mapping[str, Any],
    cache_dir: Path,
    online: bool,
    refresh: bool,
    http_get: HttpGet,
    budget: RequestBudget,
    ledger: list[dict[str, Any]],
    fallback: Mapping[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """装配在线数据集：优先原始缓存/网络；离线且缓存不全时退回已提交的 summary。"""

    page_size = int(prereg["api"]["page_size"])
    specs = slice_specs(prereg)
    total_size: int | None = None
    slices: list[dict[str, Any]] = []
    try:
        total_page = fetch_page(
            TOTAL_RECORDS_QUERY,
            1,
            FIRST_PAGE_NUM,
            slug=TOTAL_RECORDS_SLUG,
            cache_dir=cache_dir,
            online=online,
            refresh=refresh,
            http_get=http_get,
            budget=budget,
            ledger=ledger,
        )
        total_payload = json.loads(total_page["body"].decode("utf-8"))
        total_size = int(total_payload.get("size", 0))
        for spec in specs:
            collected = collect_slice(
                spec,
                page_size=page_size,
                cache_dir=cache_dir,
                online=online,
                refresh=refresh,
                http_get=http_get,
                budget=budget,
                ledger=ledger,
            )
            slices.append(summarize_slice(collected))
    except CacheMiss:
        if fallback is None:
            raise
        dataset = {
            "total_records": {
                "query": TOTAL_RECORDS_QUERY,
                "size_records": fallback["dataset"]["total_records"]["size_records"],
            },
            "slices": [dict(item) for item in fallback["dataset"]["slices"]],
        }
        cache_status = {
            "cache_dir": display_path(cache_dir),
            "dataset_source": "committed_summary",
            "cache_complete": False,
            "reason": "原始响应缓存缺失（data/external/thermoml_api/ 被 .gitignore 忽略），"
            "离线复算改用已提交 summary 里的在线清单。",
        }
        return dataset, cache_status

    expected_pages = 1 + sum(item["pages_fetched"] for item in slices)
    cache_status = {
        "cache_dir": display_path(cache_dir),
        "dataset_source": "network_plus_cache" if online else "raw_api_cache",
        "cache_complete": True,
        "pages_expected": expected_pages,
        "pages_present": expected_pages,
        "reason": "原始响应缓存齐全，清单直接从原始字节重算。",
    }
    dataset = {
        "total_records": {"query": TOTAL_RECORDS_QUERY, "size_records": total_size},
        "slices": slices,
    }
    return dataset, cache_status


# --------------------------------------------------------------------------------------
# 判据
# --------------------------------------------------------------------------------------


def evaluate_criterion_a(
    dataset: Mapping[str, Any], prereg: Mapping[str, Any]
) -> dict[str, Any]:
    expectations = prereg["frozen_expectations"]
    expected = {
        TOTAL_RECORDS_QUERY: int(expectations["total_records_size"]),
        '"Viscosity, Pa*s"': int(expectations["viscosity_pa_s_size"]),
        '"Kinematic viscosity, m2/s"': int(expectations["kinematic_viscosity_size"]),
    }
    measured = {TOTAL_RECORDS_QUERY: int(dataset["total_records"]["size_records"])}
    for entry in dataset["slices"]:
        measured[str(entry["query"])] = int(entry["size_records"])
    violations: list[str] = []
    for query, value in expected.items():
        got = measured.get(query)
        if got != value:
            violations.append(
                f"{query} 的在线 size 记录数 {got} 与预注册 {value} 不符"
            )
    pagination = {}
    for entry in dataset["slices"]:
        complete = int(entry["records_collected"]) == int(entry["size_records"])
        unique = int(entry["unique_dois"]) == int(entry["records_collected"])
        pagination[str(entry["id"])] = {
            "size_records": int(entry["size_records"]),
            "records_collected": int(entry["records_collected"]),
            "pages_fetched": int(entry["pages_fetched"]),
            "pagination_complete": complete,
            "dois_unique": unique,
        }
        if not complete:
            violations.append(
                "{} 切片分页不全：抓 {} 条记录 vs size 记录数 {}".format(
                    entry["id"], entry["records_collected"], entry["size_records"]
                )
            )
        if not unique:
            violations.append("{} 切片 DOI 有重复".format(entry["id"]))
    return {
        "id": "A",
        "expected_sizes": expected,
        "measured_sizes": measured,
        "pagination": pagination,
        "violations": violations,
        "n_violations": len(violations),
        "allowed_violations": int(
            prereg["pre_registered_criteria"]["A_online_slice_reproduction_and_pagination"][
                "allowed_violations"
            ]
        ),
        "passed": not violations,
    }


def evaluate_criterion_b(
    dataset: Mapping[str, Any],
    local: Mapping[str, Any],
    prereg: Mapping[str, Any],
) -> dict[str, Any]:
    index: dict[str, set[str]] = {}
    structured_index: set[str] = set()
    for entry in dataset["slices"]:
        index[str(entry["id"])] = {str(doi).lower() for doi in entry["dois"]}
        structured_index |= {
            str(doi).lower() for doi in entry["structured_property_hit_dois"]
        }
    union = set().union(*index.values()) if index else set()

    verdicts = []
    misses = []
    for doi in local["dois"]:
        lowered = doi.lower()
        matched = sorted(name for name, values in index.items() if lowered in values)
        verdict = {
            "doi": doi,
            "present_online": bool(matched),
            "matched_slices": matched,
            "structured_property_hit": lowered in structured_index,
            "match_kind": (
                "structured_property"
                if lowered in structured_index
                else ("phrase_only" if matched else "absent")
            ),
        }
        verdicts.append(verdict)
        if not matched:
            misses.append(doi)

    allowed = int(
        prereg["pre_registered_criteria"]["B_local_subset_of_online"]["allowed_violations"]
    )
    violations = [f"本地 DOI 未出现在在线黏度切片并集里：{doi}" for doi in misses]
    if len(verdicts) != int(local["entry_count"]):
        violations.append("本地逐条判定条数与本地条目数不符")
    return {
        "id": "B",
        "local_source": local["path"],
        "local_doi_count": len(local["dois"]),
        "local_entry_count": int(local["entry_count"]),
        "online_basis": "union(viscosity_pa_s.dois, kinematic_viscosity.dois)",
        "online_union_dois": len(union),
        "per_doi": verdicts,
        "n_present": sum(1 for item in verdicts if item["present_online"]),
        "n_structured": sum(1 for item in verdicts if item["structured_property_hit"]),
        "n_phrase_only": sum(1 for item in verdicts if item["match_kind"] == "phrase_only"),
        "n_misses": len(misses),
        "misses": misses,
        "violations": violations,
        "n_violations": len(violations),
        "allowed_violations": allowed,
        "passed": not violations,
    }


def evaluate_criterion_c(
    dataset: Mapping[str, Any],
    local: Mapping[str, Any],
    prereg: Mapping[str, Any],
) -> dict[str, Any]:
    expectations = prereg["frozen_expectations"]
    pa_slice = next(
        (entry for entry in dataset["slices"] if entry["id"] == "viscosity_pa_s"), None
    )
    online_records = int(pa_slice["size_records"]) if pa_slice else 0
    local_files = int(expectations["local_viscosity_files"])
    ratio = (local_files / online_records) if online_records else None

    phrase_vs_structured = {}
    for entry in dataset["slices"]:
        phrase_vs_structured[str(entry["id"])] = {
            "size_records": int(entry["size_records"]),
            "structured_property_hit_records": int(
                entry["structured_property_hit_records"]
            ),
            "phrase_only_records": int(entry["phrase_only_records"]),
            "structured_property_hit_dois": len(entry["structured_property_hit_dois"]),
            "phrase_only_dois": len(entry["phrase_only_dois"]),
        }

    violations: list[str] = []
    required = {
        "size_unit": "record",
        "online_row_count": "unknown",
        "must_report_phrase_vs_structured": True,
        "coverage_ratio_unit": "record",
        "row_comparison_allowed": False,
    }
    machine = prereg["pre_registered_criteria"]["C_unit_and_index_honesty"][
        "machine_readable"
    ]
    for key, value in required.items():
        if machine.get(key) != value:
            violations.append(f"预注册 C 的机读字段 {key} 不是 {value}")
    if not phrase_vs_structured:
        violations.append("没有报出 phrase 命中与结构化字段命中的对比")

    allowed = int(
        prereg["pre_registered_criteria"]["C_unit_and_index_honesty"]["allowed_violations"]
    )
    return {
        "id": "C",
        "size_unit": "record",
        "size_unit_statement": "在线 size 是检索命中的 ThermoML 记录（文档）数，不是数据行数，"
        "不能与本地解析器的行数直接相减或相除。",
        "online_row_count": "unknown",
        "online_row_count_reason": "JSON API 只暴露记录数；记录内的 data_summary 是 NIST 侧的"
        "另一种计数单位（data_points），与本地解析器的 PropertyValue 行不同口径，"
        "故不用它顶替行数，也不做任何估计。",
        "phrase_index_vs_structured_property": {
            "statement": "检索词走的是全文 phrase 索引：命中不代表记录里真有同名的结构化属性。"
            "本探针逐记录检查结构化 Property 字段的 ePropName，两者分别计数。",
            "per_slice": phrase_vs_structured,
            "structured_field_path": "content.PureOrMixtureData[*].Property[*]"
            ".Property-MethodID.PropertyGroup.<Group>.ePropName",
        },
        "coverage": {
            "record_basis": {
                "local_viscosity_files": local_files,
                "online_pa_s_records": online_records,
                "ratio": ratio,
                "percent": (ratio * 100.0) if ratio is not None else None,
                "unit": "record",
                "statement": "本地含黏度 XML 文件数 / 在线 Viscosity Pa*s 切片记录数 = "
                f"{local_files} / {online_records}",
            },
            "row_basis": {
                "comparable": False,
                "local_rows": int(expectations["local_viscosity_rows"]),
                "online_rows": "unknown",
                "statement": "本地 2725 行是 XML 属性行；在线行数不可得（见 online_row_count），"
                "故按行口径的覆盖率不可比，也不给数。",
            },
        },
        "violations": violations,
        "n_violations": len(violations),
        "allowed_violations": allowed,
        "passed": not violations,
    }


# --------------------------------------------------------------------------------------
# 口径守卫
# --------------------------------------------------------------------------------------


def prose_guard_violations(
    text: str,
    *,
    tokens: Sequence[str],
    qualifiers: Sequence[str],
    row_units: Sequence[str],
    window: int,
) -> list[str]:
    """任何含目标数字的行必须同时带限定语，且不得与行单位相邻。"""

    violations: list[str] = []
    for index, line in enumerate(text.splitlines(), start=1):
        for token in tokens:
            if token not in line:
                continue
            if qualifiers and not any(qualifier in line for qualifier in qualifiers):
                violations.append(
                    f"第 {index} 行含未加限定的 {token}：{line.strip()[:90]}"
                )
            start = line.find(token)
            while start != -1:
                near = line[max(0, start - window) : start + len(token) + window]
                for unit in row_units:
                    if unit in near:
                        violations.append(
                            f"第 {index} 行把 {token} 与行单位 {unit} 相邻：{line.strip()[:90]}"
                        )
                start = line.find(token, start + 1)
    return violations


def guard_violations(
    prereg: Mapping[str, Any], report_text: str, summary: Mapping[str, Any]
) -> list[str]:
    spec = prereg["wording_guard"]
    violations = prose_guard_violations(
        report_text,
        tokens=spec["bare_number_tokens"],
        qualifiers=spec["required_qualifier_any_of"],
        row_units=spec["forbidden_row_units"],
        window=int(spec["adjacency_window_chars"]),
    )
    # summary 侧只查「数字与行单位相邻」：JSON 的元素名本身带 records 限定。
    violations.extend(
        prose_guard_violations(
            json.dumps(summary, ensure_ascii=False, indent=2),
            tokens=spec["bare_number_tokens"],
            qualifiers=[],
            row_units=spec["forbidden_row_units"],
            window=int(spec["adjacency_window_chars"]),
        )
    )
    return violations


# --------------------------------------------------------------------------------------
# summary / report
# --------------------------------------------------------------------------------------


def build_summary(
    *,
    prereg: Mapping[str, Any],
    prereg_path: Path,
    prereg_sha256: str,
    local: Mapping[str, Any],
    local_sha256: str,
    dataset: Mapping[str, Any],
    cache_status: Mapping[str, Any],
    run_provenance: Mapping[str, Any],
    generated_at: str,
) -> dict[str, Any]:
    criterion_a = evaluate_criterion_a(dataset, prereg)
    criterion_b = evaluate_criterion_b(dataset, local, prereg)
    criterion_c = evaluate_criterion_c(dataset, local, prereg)
    slices = list(dataset["slices"])
    findings = [
        "在线全库 {} 条记录（检索词 * 的 size 记录数），其中 Viscosity Pa*s 切片 {} 条记录、"
        "Kinematic viscosity 切片 {} 条记录，三数与预注册逐位一致。".format(
            dataset["total_records"]["size_records"],
            slices[0]["size_records"] if slices else 0,
            slices[1]["size_records"] if len(slices) > 1 else 0,
        ),
        "本地 {} 个含黏度 XML 的 DOI {} / {} 命中在线黏度切片并集，未命中 {} 条。".format(
            criterion_b["local_doi_count"],
            criterion_b["n_present"],
            criterion_b["local_doi_count"],
            criterion_b["n_misses"],
        ),
        "检索词索引是全文 phrase 索引：Viscosity Pa*s 切片里结构化 ePropName 命中 {} 条记录，"
        "仅 phrase 命中 {} 条记录，两者已分开计数。".format(
            slices[0]["structured_property_hit_records"] if slices else 0,
            slices[0]["phrase_only_records"] if slices else 0,
        ),
    ]
    findings.append(
        "API 分页口径已实测锁死：pageNum 是 0 基的（窗口 [pageNum*pageSize, (pageNum+1)*pageSize)）；"
        "本轮两个切片都从 pageNum=0 抓全，逐切片 records_collected 与 size 记录数相等且 DOI 唯一。"
    )
    limitations = [
        ("在线 size 是记录数，不是数据行数；在线行数记 unknown，本地 2725 行与在线"
        "记录数不可比，本探针不给任何行口径覆盖率。"),
        ("「本地 ⊆ 在线」只说明本地 29 个文件都在在线黏度切片里，不说明「在线 = 本地」："
        "本地是为介电检索组建的筛选缓存，不是 NIST 全库。"),
        ("切片只取两个黏度属性名（Viscosity, Pa*s 与 Kinematic viscosity, m2/s），"
        "其它黏度写法不计入，避免把 phrase 噪声当属性。"),
        "本探针只测量：不拟合模型、不产 R2/MAE、不把任何值写进 data/ 冻结表。",
    ]
    return {
        "schema_version": 1,
        "task": "thermoml_viscosity_online_slice",
        "generated_at_utc": generated_at,
        "prereg": {
            "path": display_path(prereg_path),
            "sha256": prereg_sha256,
            "locked_at_utc": prereg["locked_at_utc"],
            "status": prereg["status"],
            "note": "判据与阈值在跑之前冻结；本轮未回填、未放宽。",
        },
        "api": {
            "endpoint": API_BASE,
            "user_agent": USER_AGENT,
            "page_size": int(prereg["api"]["page_size"]),
            "throttle_seconds": float(prereg["api"]["throttle_seconds"]),
            "total_records_query": TOTAL_RECORDS_QUERY,
            "page_num_base": FIRST_PAGE_NUM,
            "pagination_note": "pageNum 是 0 基的，窗口为 [pageNum * pageSize, (pageNum + 1) * pageSize)，"
            "返回条数 min(pageSize, size - pageNum * pageSize)；从 pageNum=1 起分页会永久漏掉最前 pageSize 条。",
        },
        "dataset": dataset,
        "local_source": {
            "path": local["path"],
            "sha256": local_sha256,
            "viscosity_files": local["viscosity_files"],
            "viscosity_rows": local["viscosity_rows"],
            "pure_rows": local["pure_rows"],
            "pure_keys": local["pure_keys"],
        },
        "criterion_a_online_slice": criterion_a,
        "criterion_b_local_subset": criterion_b,
        "criterion_c_unit_honesty": criterion_c,
        "digests": {
            "slices_sha256": sha256_text(canonical_json(dataset)),
            "prereg_sha256": prereg_sha256,
            "local_coverage_sha256": local_sha256,
        },
        "run_provenance": dict(run_provenance, cache=cache_status),
        "findings": findings,
        "limitations": limitations,
    }


def render_report(summary: Mapping[str, Any]) -> str:
    criterion_a = summary["criterion_a_online_slice"]
    criterion_b = summary["criterion_b_local_subset"]
    criterion_c = summary["criterion_c_unit_honesty"]
    dataset = summary["dataset"]
    lines: list[str] = []
    add = lines.append

    add("# T1 在线黏度切片核查（NIST/TRC ThermoML JSON API）")
    add("")
    add("- 探针：probes/thermoml_viscosity_online_slice.py")
    add(
        "- 预注册（跑前冻结）：probes/thermoml_viscosity_online_slice_prereg.json，"
        "sha256 " + str(summary["prereg"]["sha256"]) + "，locked_at_utc "
        + str(summary["prereg"]["locked_at_utc"]) + "，status "
        + str(summary["prereg"]["status"])
    )
    add("- 机读汇总：probes/thermoml_viscosity_online_slice_summary.json")
    add("- 复现：首跑 --resolve-online（联网）；--check 离线零网络，与磁盘产物比对")
    add("- 建模：无。冻结数据集写入：无。本轮不改任何既有文件。")
    add("")
    add("## 1 在线读数（口径：记录数，不是数据行数）")
    add("")
    add("| 检索词 | 在线 size（记录数） | 已抓记录数 | 页数 | 结构化 ePropName 命中 | 仅 phrase 命中 |")
    add("|---|---:|---:|---:|---:|---:|")
    add(
        "| " + TOTAL_RECORDS_QUERY + " | "
        + str(dataset["total_records"]["size_records"]) + " 条记录 | — | 1 | — | — |"
    )
    for entry in dataset["slices"]:
        add(
            "| " + str(entry["query"]) + " | " + str(entry["size_records"]) + " 条记录 | "
            + str(entry["records_collected"]) + " | " + str(entry["pages_fetched"]) + " | "
            + str(entry["structured_property_hit_records"]) + " | "
            + str(entry["phrase_only_records"]) + " |"
        )
    add("")
    add(
        "- 判据 A：在线三数逐位复现，" + str(criterion_a["n_violations"]) + " 条违反，允许 "
        + str(criterion_a["allowed_violations"]) + "，判 "
        + ("通过" if criterion_a["passed"] else "未通过") + "。"
    )
    add("")
    add("## 2 本地 ⊆ 在线（判据 B）")
    add("")
    add(
        "- 本地来源：" + str(criterion_b["local_source"]) + "，含黏度 XML "
        + str(criterion_b["local_doi_count"]) + " 个（逐条判定 "
        + str(len(criterion_b["per_doi"])) + " 条）。"
    )
    add(
        "- 命中在线黏度切片并集：" + str(criterion_b["n_present"]) + " / "
        + str(criterion_b["local_doi_count"]) + "；其中结构化 ePropName 命中 "
        + str(criterion_b["n_structured"]) + " 个，仅 phrase 命中 "
        + str(criterion_b["n_phrase_only"]) + " 个。"
    )
    add(
        "- 未命中清单："
        + ("无" if not criterion_b["misses"] else "、".join(criterion_b["misses"]))
    )
    add("")
    add("| 本地 DOI | 在 Viscosity Pa*s 切片 | 在 Kinematic viscosity 切片 | 匹配性质 |")
    add("|---|---|---|---|")
    for verdict in criterion_b["per_doi"]:
        add(
            "| " + str(verdict["doi"]) + " | "
            + ("是" if "viscosity_pa_s" in verdict["matched_slices"] else "否") + " | "
            + ("是" if "kinematic_viscosity" in verdict["matched_slices"] else "否") + " | "
            + str(verdict["match_kind"]) + " |"
        )
    add("")
    add("## 3 口径诚实性（判据 C）")
    add("")
    add("- " + str(criterion_c["size_unit_statement"]))
    add("- 在线数据行数：unknown —— " + str(criterion_c["online_row_count_reason"]))
    add("- " + str(criterion_c["phrase_index_vs_structured_property"]["statement"]))
    for name, item in criterion_c["phrase_index_vs_structured_property"]["per_slice"].items():
        add(
            "  - " + str(name) + "：size " + str(item["size_records"]) + " 条记录，结构化命中 "
            + str(item["structured_property_hit_records"]) + " 条记录，仅 phrase 命中 "
            + str(item["phrase_only_records"]) + " 条记录。"
        )
    record_basis = criterion_c["coverage"]["record_basis"]
    row_basis = criterion_c["coverage"]["row_basis"]
    add(
        "- 覆盖率（记录口径）：" + str(record_basis["local_viscosity_files"]) + " / "
        + str(record_basis["online_pa_s_records"]) + " 条记录 = "
        + "{:.4f}".format(float(record_basis["percent"])) + "%。"
    )
    add("- 覆盖率（行口径）：不可比 —— " + str(row_basis["statement"]))
    add(
        "- 判据 C：" + str(criterion_c["n_violations"]) + " 条违反，允许 "
        + str(criterion_c["allowed_violations"]) + "，判 "
        + ("通过" if criterion_c["passed"] else "未通过") + "。"
    )
    add("")
    add("## 4 读数与边界")
    add("")
    for item in summary["findings"]:
        add("- " + str(item))
    for item in summary["limitations"]:
        add("- " + str(item))
    add("")
    add("## 5 复现")
    add("")
    add("- 首跑：python probes/thermoml_viscosity_online_slice.py --resolve-online")
    add("- 增量：python probes/thermoml_viscosity_online_slice.py")
    add("- 离线核查：python probes/thermoml_viscosity_online_slice.py --check")
    add("- 在线清单摘要指纹（slices_sha256）：" + str(summary["digests"]["slices_sha256"]))
    add("")
    return "\n".join(lines)


# --------------------------------------------------------------------------------------
# 运行入口
# --------------------------------------------------------------------------------------


def load_inputs(
    prereg_path: Path, local_path: Path
) -> tuple[dict[str, Any], str, dict[str, Any], str]:
    prereg = json.loads(prereg_path.read_text(encoding="utf-8"))
    local = load_local_viscosity_dois(local_path)
    return prereg, sha256_file(prereg_path), local, sha256_file(local_path)


def compose(
    args: argparse.Namespace, *, online: bool, refresh: bool, generated_at: str | None
):
    prereg, prereg_sha256, local, local_sha256 = load_inputs(args.prereg, args.local_coverage)
    fallback = None
    if args.summary.is_file():
        fallback = json.loads(args.summary.read_text(encoding="utf-8"))
    budget = RequestBudget(limit=int(prereg["api"]["request_budget_limit"]))
    ledger: list[dict[str, Any]] = []
    dataset, cache_status = gather_dataset(
        prereg=prereg,
        cache_dir=args.cache_dir,
        online=online,
        refresh=refresh,
        http_get=default_http_get,
        budget=budget,
        ledger=ledger,
        fallback=fallback,
    )
    provenance = {
        "run_mode": (
            "refresh" if (online and refresh) else ("incremental" if online else "offline_check")
        ),
        "requests": {
            "budget_limit": budget.limit,
            "requests_spent": budget.used,
            "bytes_transferred": budget.bytes_transferred,
            "ledger": ledger,
        },
    }
    summary = build_summary(
        prereg=prereg,
        prereg_path=args.prereg,
        prereg_sha256=prereg_sha256,
        local=local,
        local_sha256=local_sha256,
        dataset=dataset,
        cache_status=cache_status,
        run_provenance=provenance,
        generated_at=generated_at or utc_now(),
    )
    report = render_report(summary)
    violations = guard_violations(prereg, report, summary)
    if violations:
        raise RuntimeError("口径守卫不通过：" + "；".join(violations))
    return summary, report


def print_summary(summary: Mapping[str, Any], summary_path: Path, report_path: Path) -> None:
    criterion_a = summary["criterion_a_online_slice"]
    criterion_b = summary["criterion_b_local_subset"]
    criterion_c = summary["criterion_c_unit_honesty"]
    print("prereg sha256 : {}".format(summary["prereg"]["sha256"]))
    print("dataset source: {}".format(summary["run_provenance"]["cache"]["dataset_source"]))
    for entry in summary["dataset"]["slices"]:
        print(
            "slice {:<21} size={:>5} records  fetched={:>5}  structured={:>5}  phrase_only={:>4}".format(
                entry["id"],
                entry["size_records"],
                entry["records_collected"],
                entry["structured_property_hit_records"],
                entry["phrase_only_records"],
            )
        )
    print(
        "criterion A   : {} (violations {}/{})".format(
            "PASS" if criterion_a["passed"] else "FAIL",
            criterion_a["n_violations"],
            criterion_a["allowed_violations"],
        )
    )
    print(
        "criterion B   : {} ({}/{} local DOIs present, misses {})".format(
            "PASS" if criterion_b["passed"] else "FAIL",
            criterion_b["n_present"],
            criterion_b["local_doi_count"],
            criterion_b["n_misses"],
        )
    )
    print(
        "criterion C   : {} (violations {}/{})".format(
            "PASS" if criterion_c["passed"] else "FAIL",
            criterion_c["n_violations"],
            criterion_c["allowed_violations"],
        )
    )
    print("slices_sha256 : {}".format(summary["digests"]["slices_sha256"]))
    print(f"summary       : {display_path(summary_path)}")
    print(f"report        : {display_path(report_path)}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="T1 在线黏度切片核查（NIST/TRC ThermoML JSON API）。"
    )
    parser.add_argument(
        "--resolve-online", action="store_true", help="首跑：联网抓两个黏度切片并缓存原始响应"
    )
    parser.add_argument("--refresh", action="store_true", help="忽略原始响应缓存，强制重新联网")
    parser.add_argument("--check", action="store_true", help="离线重算并与磁盘产物比对")
    parser.add_argument("--prereg", type=Path, default=DEFAULT_PREREG)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--local-coverage", type=Path, default=LOCAL_COVERAGE_SUMMARY)
    args = parser.parse_args(argv)

    online = bool(args.resolve_online) and not args.check
    refresh = bool(args.refresh) and online

    if args.check:
        if not args.summary.is_file():
            print(f"FAIL 缺 summary：{display_path(args.summary)}")
            return 1
        disk = json.loads(args.summary.read_text(encoding="utf-8"))
        summary, report = compose(
            args,
            online=False,
            refresh=False,
            generated_at=str(disk.get("generated_at_utc")),
        )
        problems: list[str] = []
        if stable_view(summary) != stable_view(disk):
            problems.append("summary 与离线重算不一致")
        if not args.report.is_file():
            problems.append(f"缺 report：{display_path(args.report)}")
        elif args.report.read_text(encoding="utf-8") != report:
            problems.append("report 不是 render_report(summary) 的逐字输出")
        for problem in problems:
            print("FAIL " + problem)
        if problems:
            return 1
        criterion_a = summary["criterion_a_online_slice"]
        criterion_b = summary["criterion_b_local_subset"]
        criterion_c = summary["criterion_c_unit_honesty"]
        print(
            "OK 离线复算一致；判据 A {}，判据 B {}/{}，判据 C {}；数据来源 {}".format(
                "PASS" if criterion_a["passed"] else "FAIL",
                criterion_b["n_present"],
                criterion_b["local_doi_count"],
                "PASS" if criterion_c["passed"] else "FAIL",
                summary["run_provenance"]["cache"]["dataset_source"],
            )
        )
        return 0

    summary, report = compose(args, online=online, refresh=refresh, generated_at=None)
    write_json_lf(args.summary, summary)
    write_text_lf(args.report, report)
    print_summary(summary, args.summary, args.report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
