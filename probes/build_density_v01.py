r"""W17-4 加维度①·密度 rho(T)：把纯组分密度观测从 NIST/TRC ThermoML 建成 density_v01 新表。

双用途：(a) 解锁本地 176 行运动黏度（kappa = eta / rho，本表给 rho(T)）；(b) 作为筛选维度
（液相窗口 / 体积能量密度）。

数据源分两层，跑前侦察实测锁死：
  目录层：/ThermoML-API/objects 这个 JSON 检索 API，检索词 "Density, kg/m3"（size 记录数 4697）。
    该 API 的 pageNum 是 0 基的：窗口 [pageNum * pageSize, (pageNum + 1) * pageSize)。
  数值层：同源的 ThermoML XML（https://trc.nist.gov/ThermoML/{doi}.xml）。
    侦察实测：JSON API 只带 Citation / Compound / PureOrMixtureData 的定义与 data_summary 计数，
    整页 100 条记录里 "nValue" 出现 0 次、"PropertyValue" 出现 0 次，实测单对象端点与 ?full=true
    同样无数值。所以 rho(T) 的数值只能从 XML 取——本探针把这条口径写进 summary，不假装
    JSON API 里有观测行。

四件判据在跑之前冻结在 probes/build_density_v01_prereg.json 里：
  A 目录层逐位复现（* 11923 / Density 切片 4697，抓全 47 页，DOI 唯一，零失败页）；
  B 数值层自洽（纯组分、属性名、单位表、T/rho 区间、拒绝账本相加等于命中总行）；
  C 解冻指标逐行可复算（176 行运动黏度配到密度的行数，exact 与 <=1.0 K 两个口径）；
  D 口径诚实性（目录层是记录数、在线行数记 unknown、短语命中与结构化 ePropName 命中分开报）。

不做：不拟合任何模型、不产 R2/MAE、不改任何既有文件、不把任何值写进六件冻结件。

用法（PowerShell，仓库根）：
    .\.venv\Scripts\python.exe probes/build_density_v01.py --resolve-online   # 首跑：联网
    .\.venv\Scripts\python.exe probes/build_density_v01.py                    # 增量：缓存已有的不再联网
    .\.venv\Scripts\python.exe probes/build_density_v01.py --check            # 离线重算并与磁盘产物比对
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import hashlib
import json
import math
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from electrolyte_ml.thermoml import parse_thermoml_file

API_BASE = "https://trc.nist.gov/ThermoML-API/objects"
XML_BASE = "https://trc.nist.gov/ThermoML"
USER_AGENT = "electrolyte-ml/0.0.0 (+https://trc.nist.gov/ThermoML/)"
HTTP_TIMEOUT_SECONDS = 120
THROTTLE_SECONDS = 0.25
PAGE_SIZE = 100
FIRST_PAGE_NUM = 0
REQUEST_BUDGET_LIMIT = 20000

TOTAL_RECORDS_QUERY = "*"
TOTAL_RECORDS_SLUG = "total_records"
DENSITY_QUERY = '"Density, kg/m3"'
DENSITY_SLUG = "density_kg_m3"

MASS_DENSITY_NAME = "Mass density, kg/m3"
CRITICAL_DENSITY_NAME = "Critical density, kg/m3"
ACCEPTED_PROPERTY_NAMES: tuple[str, ...] = ("mass density, kg/m3", "density, kg/m3")

UNIT_TO_KG_M3: dict[str, float] = {
    "kg/m3": 1.0,
    "g/cm3": 1000.0,
    "g/mL": 1000.0,
    "g/ml": 1000.0,
    "kg/L": 1000.0,
    "kg/l": 1000.0,
    "kg/dm3": 1000.0,
    "g/L": 1.0,
    "g/l": 1.0,
}

MIN_T_K = 100.0
MAX_T_K = 1000.0
MIN_RHO_KG_M3 = 1.0
MAX_RHO_KG_M3 = 5000.0
EXACT_T_TOLERANCE_K = 1e-3
NEAREST_T_TOLERANCE_K = 1.0

XML_WORKERS = 8
XML_POLITENESS_SECONDS = 0.05
XML_RETRIES = 2

KINEMATIC_PROPERTY = "Kinematic viscosity, m2/s"

DEFAULT_PREREG = REPOSITORY_ROOT / "probes" / "build_density_v01_prereg.json"
DEFAULT_SUMMARY = REPOSITORY_ROOT / "probes" / "density_v01_summary.json"
DEFAULT_REPORT = REPOSITORY_ROOT / "reports" / "density_v01.md"
DEFAULT_CATALOG_CACHE = REPOSITORY_ROOT / "data" / "external" / "thermoml_api"
DEFAULT_XML_CACHE = REPOSITORY_ROOT / "data" / "raw" / "thermoml_density"
DEFAULT_TABLE = REPOSITORY_ROOT / "data" / "density_v01.csv"
DEFAULT_RAW = REPOSITORY_ROOT / "data" / "processed" / "density_raw.csv"
DEFAULT_DIELECTRIC = REPOSITORY_ROOT / "data" / "dielectric_v03.csv"
DEFAULT_IDENTITY_MAP = REPOSITORY_ROOT / "data" / "reference" / "identity_map.csv"
DEFAULT_KINEMATIC = (
    REPOSITORY_ROOT / "data" / "processed" / "viscosity_observations_thermoml.csv"
)

# 这两个 key 天然随运行变化（时间戳、本次请求记账与缓存命中），比对时剔除。
UNSTABLE_SUMMARY_KEYS: tuple[str, ...] = ("generated_at_utc", "run_provenance")

TABLE_COLUMNS: tuple[str, ...] = (
    "inchikey",
    "smiles",
    "name",
    "T_K",
    "density_kg_m3",
    "pressure_kPa",
    "phase",
    "uncertainty",
    "source_doi",
    "thermoml_file",
    "source_row_index",
)

RAW_COLUMNS: tuple[str, ...] = (
    "inchikey",
    "inchi",
    "smiles",
    "name",
    "T_K",
    "property_name",
    "property_value_raw",
    "property_unit_raw",
    "density_kg_m3",
    "unit_conversion_factor",
    "quality_flag",
    "uncertainty",
    "uncertainty_kind",
    "phase",
    "method_name",
    "pressure_kPa",
    "source_doi",
    "thermoml_file",
    "source_row_index",
)


class BudgetExhausted(RuntimeError):
    """请求数超过预注册预算时抛出。"""


class ThermoMLSearchError(RuntimeError):
    """检索 API 返回非 200 或缺页时抛出。"""


class CacheMiss(RuntimeError):
    """离线模式下原始缓存缺失时抛出。"""


class ValueLayerUnavailable(RuntimeError):
    """数值层（XML 缓存）在离线模式下不可用时抛出。"""


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


# 本机环境变量代理指向失效端口（见 prereg.direct_connection_note），NIST TRC 可直连。
DIRECT_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def default_http_get(url: str, *, timeout: int = HTTP_TIMEOUT_SECONDS) -> HttpResponse:
    """唯一的上网出口；测试里整体替换成 fake。"""

    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with DIRECT_OPENER.open(request, timeout=timeout) as response:
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
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


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


def write_csv_lf(path: Path, fieldnames: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def stable_view(summary: Mapping[str, Any]) -> dict[str, Any]:
    clone = json.loads(json.dumps(summary, ensure_ascii=False))
    for key in UNSTABLE_SUMMARY_KEYS:
        clone.pop(key, None)
    return clone


def to_float(text: Any) -> float | None:
    try:
        value = float(str(text).strip())
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def fmt_number(value: float) -> str:
    return f"{value:.12g}"


# --------------------------------------------------------------------------------------
# HTTP + 原始响应缓存（目录层）
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
# 目录层解析
# --------------------------------------------------------------------------------------


def record_doi(record: Mapping[str, Any]) -> str:
    identifier = record.get("id")
    if isinstance(identifier, str) and ".thermoml/" in identifier:
        return identifier.split(".thermoml/", 1)[1]
    content = record.get("content")
    if isinstance(content, Mapping):
        citation = content.get("Citation")
        if isinstance(citation, Mapping):
            doi = citation.get("sDOI")
            if isinstance(doi, str):
                return doi.strip()
    return ""


def block_property_names(block: Mapping[str, Any]) -> set[str]:
    names: set[str] = set()
    for prop in block.get("Property", []) or []:
        if not isinstance(prop, Mapping):
            continue
        group = prop.get("Property-MethodID", {})
        if not isinstance(group, Mapping):
            continue
        property_group = group.get("PropertyGroup", {})
        if not isinstance(property_group, Mapping):
            continue
        for value in property_group.values():
            if isinstance(value, Mapping) and isinstance(value.get("ePropName"), str):
                names.add(value["ePropName"].strip())
    return names


def content_compound_keys(content: Mapping[str, Any]) -> set[str]:
    keys: set[str] = set()
    for compound in content.get("Compound", []) or []:
        if not isinstance(compound, Mapping):
            continue
        key = compound.get("sStandardInChIKey")
        if isinstance(key, str) and key.strip():
            keys.add(key.strip())
    return keys


def block_component_keys(block: Mapping[str, Any]) -> set[str]:
    keys: set[str] = set()
    for component in block.get("Component", []) or []:
        if not isinstance(component, Mapping):
            continue
        key = component.get("sStandardInChIKey")
        if isinstance(key, str) and key.strip():
            keys.add(key.strip())
    return keys


def has_pure_mass_density(record: Mapping[str, Any]) -> bool:
    """目录层判定：该记录是否含纯组分 Mass density, kg/m3 数据点。"""

    content = record.get("content") or {}
    if not isinstance(content, Mapping):
        return False
    for block in content.get("PureOrMixtureData", []) or []:
        if not isinstance(block, Mapping):
            continue
        if len(block.get("Component") or []) != 1:
            continue
        if MASS_DENSITY_NAME in block_property_names(block):
            return True
    summary = content.get("data_summary") or {}
    if isinstance(summary, Mapping):
        pure = summary.get("pure") or {}
        if isinstance(pure, Mapping):
            volumetric = pure.get("VolumetricProp") or {}
            if isinstance(volumetric, Mapping):
                entry = volumetric.get(MASS_DENSITY_NAME) or {}
                if isinstance(entry, Mapping):
                    points = entry.get("data_points")
                    if isinstance(points, (int, float)) and points > 0:
                        return True
    return False


def catalog_page_descriptor(payload: Mapping[str, Any]) -> dict[str, Any]:
    records = payload.get("results", []) or []
    dois: list[str] = []
    without_doi = 0
    keys: set[str] = set()
    pure_mass_dois: list[str] = []
    property_names: dict[str, int] = {}
    records_with_mass_name = 0
    records_with_critical_name = 0
    for record in records:
        if not isinstance(record, Mapping):
            continue
        doi = record_doi(record)
        if doi:
            dois.append(doi)
        else:
            without_doi += 1
        content = record.get("content") or {}
        if not isinstance(content, Mapping):
            continue
        keys |= content_compound_keys(content)
        if has_pure_mass_density(record):
            pure_mass_dois.append(doi)
        block_names: set[str] = set()
        for block in content.get("PureOrMixtureData", []) or []:
            if not isinstance(block, Mapping):
                continue
            block_names |= block_property_names(block)
        for name in block_names:
            property_names[name] = property_names.get(name, 0) + 1
        if MASS_DENSITY_NAME in block_names:
            records_with_mass_name += 1
        if CRITICAL_DENSITY_NAME in block_names:
            records_with_critical_name += 1
    return {
        "records": len(records),
        "dois": dois,
        "without_doi": without_doi,
        "keys": keys,
        "pure_mass_dois": pure_mass_dois,
        "property_names": property_names,
        "records_with_mass_name": records_with_mass_name,
        "records_with_critical_name": records_with_critical_name,
        "size": int(payload.get("size", len(records)) or 0),
    }


# --------------------------------------------------------------------------------------
# 目录层装配
# --------------------------------------------------------------------------------------


def collect_catalog(
    *,
    cache_dir: Path,
    online: bool,
    refresh: bool,
    http_get: HttpGet,
    budget: RequestBudget,
    ledger: list[dict[str, Any]],
) -> dict[str, Any]:
    """抓全目录层：* 总记录数 + Density 切片全部 47 页。"""

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
    total_size = int(json.loads(total_page["body"].decode("utf-8")).get("size", 0))
    del total_page

    first = fetch_page(
        DENSITY_QUERY,
        PAGE_SIZE,
        FIRST_PAGE_NUM,
        slug=DENSITY_SLUG,
        cache_dir=cache_dir,
        online=online,
        refresh=refresh,
        http_get=http_get,
        budget=budget,
        ledger=ledger,
    )
    first_payload = json.loads(first["body"].decode("utf-8"))
    size = int(first_payload.get("size", len(first_payload.get("results", []))) or 0)
    pages = max(1, math.ceil(size / PAGE_SIZE))

    dois: list[str] = []
    compound_keys: set[str] = set()
    pure_mass_dois: list[str] = []
    property_names: dict[str, int] = {}
    without_doi = 0
    records_collected = 0
    records_with_mass = 0
    records_with_critical = 0
    failed_pages: list[dict[str, Any]] = []
    sources: set[str] = {str(first["source"])}

    def absorb(payload: Mapping[str, Any]) -> None:
        nonlocal records_collected, without_doi, records_with_mass, records_with_critical
        descriptor = catalog_page_descriptor(payload)
        records_collected += int(descriptor["records"])
        without_doi += int(descriptor["without_doi"])
        dois.extend(descriptor["dois"])
        compound_keys.update(descriptor["keys"])
        pure_mass_dois.extend(descriptor["pure_mass_dois"])
        records_with_mass += int(descriptor["records_with_mass_name"])
        records_with_critical += int(descriptor["records_with_critical_name"])
        for name, count in descriptor["property_names"].items():
            property_names[name] = property_names.get(name, 0) + int(count)

    absorb(first_payload)
    del first_payload
    for page_num in range(FIRST_PAGE_NUM + 1, FIRST_PAGE_NUM + pages):
        try:
            extra = fetch_page(
                DENSITY_QUERY,
                PAGE_SIZE,
                page_num,
                slug=DENSITY_SLUG,
                cache_dir=cache_dir,
                online=online,
                refresh=refresh,
                http_get=http_get,
                budget=budget,
                ledger=ledger,
            )
        except ThermoMLSearchError as exc:
            failed_pages.append({"page": page_num, "error": str(exc)})
            continue
        payload = json.loads(extra["body"].decode("utf-8"))
        sources.add(str(extra["source"]))
        absorb(payload)
        del payload

    slice_dataset = {
        "id": DENSITY_SLUG,
        "query": DENSITY_QUERY,
        "page_size": PAGE_SIZE,
        "size_records": size,
        "pages_fetched": pages,
        "records_collected": records_collected,
        "records_without_doi": without_doi,
        "unique_dois": len(set(dois)),
        "dois": sorted(set(dois)),
        "records_with_pure_mass_density": len(set(pure_mass_dois)),
        "dois_with_pure_mass_density": sorted(set(pure_mass_dois)),
        "records_with_mass_density_name": records_with_mass,
        "records_with_critical_density_name": records_with_critical,
        "structured_property_name_counts": dict(
            sorted(property_names.items(), key=lambda item: (-item[1], item[0]))
        ),
        "compound_keys": sorted(compound_keys),
        "failed_pages": failed_pages,
    }
    return {
        "total_records": {"query": TOTAL_RECORDS_QUERY, "size_records": total_size},
        "slice": slice_dataset,
        "sources": sorted(sources),
    }


# --------------------------------------------------------------------------------------
# 数值层：ThermoML XML
# --------------------------------------------------------------------------------------


def xml_url(doi: str) -> str:
    return f"{XML_BASE}/{urllib.parse.quote(doi, safe='/')}.xml"


def xml_cache_paths(cache_dir: Path, doi: str) -> tuple[Path, Path]:
    base = Path(cache_dir) / doi.replace("/", "__")
    return Path(str(base) + ".xml"), Path(str(base) + ".xml.url")


def fetch_xml(
    doi: str,
    *,
    cache_dir: Path,
    online: bool,
    refresh: bool,
    http_get: HttpGet,
    budget: RequestBudget,
    ledger: list[dict[str, Any]],
    throttle_seconds: float = XML_POLITENESS_SECONDS,
    timeout: int = HTTP_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    url = xml_url(doi)
    cache_path, marker_path = xml_cache_paths(cache_dir, doi)
    if (
        not refresh
        and cache_path.is_file()
        and marker_path.is_file()
        and marker_path.read_text(encoding="utf-8").strip() == url
    ):
        body = cache_path.read_bytes()
        return {
            "doi": doi,
            "url": url,
            "path": cache_path,
            "source": "local_cache",
            "bytes": len(body),
            "ok": True,
        }
    if not online:
        return {
            "doi": doi,
            "url": url,
            "path": cache_path,
            "source": "missing_cache",
            "bytes": 0,
            "ok": False,
        }

    last: Exception | None = None
    for attempt in range(XML_RETRIES + 1):
        with _BUDGET_LOCK:
            budget.spend()
        try:
            response = http_get(url, timeout=timeout)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last = exc
            time.sleep(throttle_seconds * (2**attempt))
            continue
        with _BUDGET_LOCK:
            budget.bytes_transferred += len(response.body)
        if response.status_code != 200:
            last = ThermoMLSearchError(f"HTTP {response.status_code}")
            time.sleep(throttle_seconds * (2**attempt))
            continue
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(response.body)
        marker_path.write_text(url + "\n", encoding="utf-8", newline="\n")
        time.sleep(throttle_seconds)
        return {
            "doi": doi,
            "url": url,
            "path": cache_path,
            "source": "network",
            "bytes": len(response.body),
            "ok": True,
        }
    return {
        "doi": doi,
        "url": url,
        "path": cache_path,
        "source": "failed",
        "bytes": 0,
        "ok": False,
        "error": str(last),
    }


def download_xmls(
    dois: Sequence[str],
    *,
    cache_dir: Path,
    online: bool,
    refresh: bool,
    http_get: HttpGet,
    budget: RequestBudget,
    ledger: list[dict[str, Any]],
    workers: int = XML_WORKERS,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    def task(doi: str) -> dict[str, Any]:
        return fetch_xml(
            doi,
            cache_dir=cache_dir,
            online=online,
            refresh=refresh,
            http_get=http_get,
            budget=budget,
            ledger=ledger,
        )

    if online and workers > 1:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(task, dois))
    else:
        results = [task(doi) for doi in dois]

    failures = [
        {"doi": r["doi"], "source": r["source"], "error": r.get("error", "")}
        for r in results
        if not r["ok"]
    ]
    status = {
        "requested": len(dois),
        "available": sum(1 for r in results if r["ok"]),
        "failed": len(failures),
        "missing_cache": sum(1 for r in results if r["source"] == "missing_cache"),
        "bytes_on_disk": sum(int(r["bytes"]) for r in results if r["ok"]),
        "failures": failures,
    }
    return results, status


# --------------------------------------------------------------------------------------
# 观测行抽取与单位归一
# --------------------------------------------------------------------------------------


_RDKIT_LOGGING_DISABLED = False


def pressure_kpa(constraints_json: str) -> str:
    try:
        constraints = json.loads(constraints_json or "[]")
    except (TypeError, ValueError):
        return ""
    if not isinstance(constraints, list):
        return ""
    for item in constraints:
        if not isinstance(item, Mapping):
            continue
        name = str(item.get("name") or "").strip()
        unit = str(item.get("unit") or "").strip()
        value = to_float(item.get("value"))
        if value is None:
            continue
        if "pressure" not in name.lower() and unit.lower() not in {
            "kpa",
            "pa",
            "mpa",
            "bar",
            "atm",
            "torr",
        }:
            continue
        lowered = unit.lower()
        if lowered == "kpa":
            return fmt_number(value)
        if lowered == "pa":
            return fmt_number(value / 1000.0)
        if lowered == "mpa":
            return fmt_number(value * 1000.0)
        if lowered == "bar":
            return fmt_number(value * 100.0)
        if lowered == "atm":
            return fmt_number(value * 101.325)
        if lowered == "torr":
            return fmt_number(value * 0.13332236842105263)
    return ""


def _disable_rdkit_logging() -> None:
    """RDKit 会把反解告警直接写到 stderr；本表只用它的 SMILES 渲染，静音即可。"""

    global _RDKIT_LOGGING_DISABLED
    if _RDKIT_LOGGING_DISABLED:
        return
    with contextlib.suppress(Exception):
        from rdkit import RDLogger

        RDLogger.DisableLog("rdApp.*")
    _RDKIT_LOGGING_DISABLED = True


def inchi_to_smiles(inchi: str, cache: dict[str, str]) -> str:
    if not inchi:
        return ""
    if inchi in cache:
        return cache[inchi]
    _disable_rdkit_logging()
    smiles = ""
    try:
        from rdkit import Chem

        molecule = Chem.MolFromInchi(inchi)
        if molecule is not None:
            smiles = Chem.MolToSmiles(molecule)
    except Exception:  # noqa: BLE001 - RDKit 反解失败会抛任意异常，留空即可
        smiles = ""
    cache[inchi] = smiles
    return smiles


def project_pure_row(row: Mapping[str, str], *, inchi_cache: dict[str, str]) -> dict[str, str]:
    unit = (row.get("property_unit") or "").strip()
    raw_value = (row.get("property_value") or "").strip()
    value = to_float(raw_value)
    t_k = to_float(row.get("temperature_value"))
    factor = UNIT_TO_KG_M3.get(unit)
    rho: float | None = None
    if value is not None and factor is not None:
        rho = value * factor

    if factor is None:
        quality = "unit_rejected"
    elif t_k is None or not (MIN_T_K < t_k < MAX_T_K):
        quality = "temperature_rejected"
    elif rho is None or not (MIN_RHO_KG_M3 < rho < MAX_RHO_KG_M3):
        quality = "value_rejected"
    else:
        quality = "accepted"

    inchi = (row.get("primary_compound_inchi") or "").strip()
    return {
        "inchikey": (row.get("primary_compound_inchi_key") or "").strip(),
        "inchi": inchi,
        "name": (row.get("primary_compound_name") or "").strip(),
        "T_K": "" if t_k is None else fmt_number(t_k),
        "property_name": (row.get("property_name") or "").strip(),
        "property_value_raw": raw_value,
        "property_unit_raw": unit,
        "density_kg_m3": "" if rho is None else fmt_number(rho),
        "unit_conversion_factor": "" if factor is None else fmt_number(factor),
        "quality_flag": quality,
        "uncertainty": (row.get("property_uncertainty") or "").strip(),
        "uncertainty_kind": (row.get("property_uncertainty_kind") or "").strip(),
        "phase": (row.get("phase") or "").strip(),
        "method_name": (row.get("method_name") or "").strip(),
        "pressure_kPa": pressure_kpa(row.get("constraints_json") or ""),
        "source_doi": (row.get("doi") or "").strip(),
        "thermoml_file": (row.get("source_file") or "").strip(),
        "source_row_index": (row.get("source_row_index") or "").strip(),
        "smiles": inchi_to_smiles(inchi, inchi_cache),
    }


def extract_value_layer(
    xml_results: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    inchi_cache: dict[str, str] = {}
    raw_rows: list[dict[str, str]] = []
    total_named_rows = 0
    multi_component_rows = 0
    parse_failures: list[dict[str, str]] = []
    for result in xml_results:
        if not result.get("ok"):
            continue
        path = Path(str(result["path"]))
        try:
            parsed = parse_thermoml_file(path)
        except Exception as exc:  # noqa: BLE001 - 解析失败必须记账，不能静默
            parse_failures.append({"file": path.name, "error": str(exc)})
            continue
        for row in parsed:
            name = (row.get("property_name") or "").strip().lower()
            if name not in ACCEPTED_PROPERTY_NAMES:
                continue
            total_named_rows += 1
            component_count = int((row.get("component_count") or "0").strip() or 0)
            if component_count != 1:
                multi_component_rows += 1
                continue
            raw_rows.append(project_pure_row(row, inchi_cache=inchi_cache))
    raw_rows.sort(
        key=lambda item: (item["thermoml_file"], int(item["source_row_index"] or "0"))
    )
    return {
        "source": "thermoml_xml",
        "raw_rows": raw_rows,
        "total_named_density_rows": total_named_rows,
        "multi_component_density_rows": multi_component_rows,
        "parse_failures": parse_failures,
        "smiles_unresolved": sum(
            1 for row in raw_rows if row["quality_flag"] == "accepted" and not row["smiles"]
        ),
    }


def table_rows_from_raw(raw_rows: Sequence[Mapping[str, str]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for row in raw_rows:
        if row["quality_flag"] != "accepted":
            continue
        rows.append({column: row.get(column, "") for column in TABLE_COLUMNS})
    rows.sort(key=lambda item: (item["thermoml_file"], int(item["source_row_index"] or "0")))
    return rows


def ledger_from_raw(raw_rows: Sequence[Mapping[str, str]]) -> dict[str, int]:
    ledger = {
        "accepted_pure_rows": 0,
        "unit_rejected": 0,
        "temperature_rejected": 0,
        "value_rejected": 0,
    }
    for row in raw_rows:
        flag = row["quality_flag"]
        if flag == "accepted":
            ledger["accepted_pure_rows"] += 1
        else:
            ledger[flag] = ledger.get(flag, 0) + 1
    return ledger


# --------------------------------------------------------------------------------------
# 覆盖率 / 温度分布 / 解冻配对
# --------------------------------------------------------------------------------------

_BUDGET_LOCK = threading.Lock()

TEMPERATURE_BINS: tuple[tuple[float | None, float | None], ...] = (
    (None, 200.0),
    (200.0, 250.0),
    (250.0, 273.15),
    (273.15, 298.15),
    (298.15, 323.15),
    (323.15, 373.15),
    (373.15, 450.0),
    (450.0, None),
)


def read_keys(path: Path, column: str) -> set[str]:
    return {
        (row.get(column) or "").strip()
        for row in read_csv_rows(path)
        if (row.get(column) or "").strip()
    }


def coverage_block(
    block_id: str, source_path: Path, target_keys: set[str], density_keys: set[str]
) -> dict[str, Any]:
    intersection = sorted(target_keys & density_keys)
    missing = sorted(target_keys - density_keys)
    fraction = (len(intersection) / len(target_keys)) if target_keys else None
    return {
        "id": block_id,
        "source": display_path(source_path),
        "unit": "compound",
        "target_size": len(target_keys),
        "density_size": len(density_keys),
        "intersection_size": len(intersection),
        "covered_fraction": fraction,
        "intersection": intersection,
        "missing_keys": missing,
    }


def temperature_distribution(rows: Sequence[Mapping[str, str]]) -> list[dict[str, Any]]:
    bins: list[dict[str, Any]] = []
    for low, high in TEMPERATURE_BINS:
        if low is None:
            label = f"T < {high:g} K"
        elif high is None:
            label = f"T >= {low:g} K"
        else:
            label = f"{low:g} <= T < {high:g} K"
        count = 0
        for row in rows:
            temperature = to_float(row.get("T_K"))
            if temperature is None:
                continue
            if (low is None or temperature >= low) and (high is None or temperature < high):
                count += 1
        bins.append({"label": label, "low_k": low, "high_k": high, "count": count})
    return bins


def pair_kinematic_rows(
    kinematic_rows: Sequence[Mapping[str, str]],
    density_rows: Sequence[Mapping[str, str]],
) -> dict[str, Any]:
    """逐行把运动黏度行配到密度行：exact（1e-3 K）与 nearest（<=1.0 K）两个口径。"""

    index: dict[str, list[tuple[float, Mapping[str, str]]]] = {}
    for row in density_rows:
        key = (row.get("inchikey") or "").strip()
        temperature = to_float(row.get("T_K"))
        if not key or temperature is None:
            continue
        index.setdefault(key, []).append((temperature, row))
    for entries in index.values():
        entries.sort(key=lambda item: item[0])

    per_row: list[dict[str, Any]] = []
    exact_rows = 0
    nearest_rows = 0
    for row in kinematic_rows:
        key = (row.get("inchikey") or "").strip()
        temperature = to_float(row.get("T_K"))
        candidates = index.get(key, [])
        exact_hit: Mapping[str, str] | None = None
        nearest_hit: tuple[float, Mapping[str, str]] | None = None
        if temperature is not None and candidates:
            for candidate_temperature, candidate in candidates:
                if abs(candidate_temperature - temperature) <= EXACT_T_TOLERANCE_K:
                    exact_hit = candidate
                    break
            best_delta = None
            for candidate_temperature, candidate in candidates:
                delta = abs(candidate_temperature - temperature)
                if delta > NEAREST_T_TOLERANCE_K:
                    continue
                if (
                    best_delta is None
                    or delta < best_delta - 1e-12
                    or (abs(delta - best_delta) <= 1e-12 and candidate_temperature < nearest_hit[0])
                ):
                    best_delta = delta
                    nearest_hit = (candidate_temperature, candidate)
        if exact_hit is not None:
            exact_rows += 1
        if nearest_hit is not None:
            nearest_rows += 1
        entry: dict[str, Any] = {
            "inchikey": key,
            "name": (row.get("name") or "").strip(),
            "T_K": "" if temperature is None else fmt_number(temperature),
            "viscosity_kinematic_m2_s": (row.get("viscosity_kinematic_m2_s") or "").strip(),
            "viscosity_source_doi": (row.get("source_doi") or "").strip(),
            "viscosity_thermoml_file": (row.get("thermoml_file") or "").strip(),
            "viscosity_source_row_index": (row.get("source_row_index") or "").strip(),
            "exact": exact_hit is not None,
            "nearest": nearest_hit is not None,
        }
        if nearest_hit is not None:
            delta = abs(nearest_hit[0] - (temperature or 0.0))
            entry["delta_t_k"] = round(delta, 6)
            entry["density_T_K"] = fmt_number(nearest_hit[0])
            entry["density_kg_m3"] = (nearest_hit[1].get("density_kg_m3") or "").strip()
            entry["nearest_source_doi"] = (nearest_hit[1].get("source_doi") or "").strip()
            entry["nearest_thermoml_file"] = (nearest_hit[1].get("thermoml_file") or "").strip()
            entry["nearest_source_row_index"] = (
                nearest_hit[1].get("source_row_index") or ""
            ).strip()
        else:
            entry["delta_t_k"] = None
            entry["density_T_K"] = ""
            entry["density_kg_m3"] = ""
            entry["nearest_source_doi"] = ""
            entry["nearest_thermoml_file"] = ""
            entry["nearest_source_row_index"] = ""
        per_row.append(entry)

    by_key: dict[str, dict[str, int]] = {}
    for entry in per_row:
        bucket = by_key.setdefault(entry["inchikey"], {"rows": 0, "exact": 0, "nearest": 0})
        bucket["rows"] += 1
        bucket["exact"] += int(entry["exact"])
        bucket["nearest"] += int(entry["nearest"])

    return {
        "local_rows": len(per_row),
        "local_keys": len(by_key),
        "exact_rows": exact_rows,
        "nearest_rows": nearest_rows,
        "exact_tolerance_k": EXACT_T_TOLERANCE_K,
        "nearest_tolerance_k": NEAREST_T_TOLERANCE_K,
        "by_key": dict(sorted(by_key.items())),
        "per_row": per_row,
    }


# --------------------------------------------------------------------------------------
# 判据
# --------------------------------------------------------------------------------------


def evaluate_criterion_a(
    dataset: Mapping[str, Any], prereg: Mapping[str, Any]
) -> dict[str, Any]:
    expected = prereg["frozen_expectations"]
    total_records = int(dataset["total_records"]["size_records"])
    slice_dataset = dataset["slice"]
    size_records = int(slice_dataset["size_records"])
    records_collected = int(slice_dataset["records_collected"])
    pages_fetched = int(slice_dataset["pages_fetched"])
    unique_dois = int(slice_dataset["unique_dois"])
    failed_pages = list(slice_dataset.get("failed_pages", []))

    violations: list[str] = []
    if total_records != int(expected["total_records_size"]):
        violations.append(
            f"* 的在线 size 记录数 {total_records} 与预注册 {expected['total_records_size']} 不符"
        )
    if size_records != int(expected["density_slice_size"]):
        violations.append(
            f"Density 切片的在线 size 记录数 {size_records} 与预注册 {expected['density_slice_size']} 不符"
        )
    if pages_fetched != int(expected["density_slice_pages"]):
        violations.append(
            f"抓取页数 {pages_fetched} 与预注册 {expected['density_slice_pages']} 不符"
        )
    if records_collected != size_records:
        violations.append(
            f"分页不全：抓到 {records_collected} 条记录 vs size 记录数 {size_records}"
        )
    if unique_dois != records_collected:
        violations.append(
            f"DOI 有重复：唯一 DOI {unique_dois} vs 抓到 {records_collected} 条记录"
        )
    if FIRST_PAGE_NUM != 0:
        violations.append("分页不是从 pageNum=0 起")
    if failed_pages:
        violations.append(f"有失败页：{failed_pages}")

    return {
        "id": "A",
        "expected_sizes": {
            "*": int(expected["total_records_size"]),
            DENSITY_QUERY: int(expected["density_slice_size"]),
        },
        "measured_sizes": {"*": total_records, DENSITY_QUERY: size_records},
        "pagination": {
            "page_size": int(slice_dataset["page_size"]),
            "page_num_base": FIRST_PAGE_NUM,
            "pages_fetched": pages_fetched,
            "expected_pages": int(expected["density_slice_pages"]),
            "records_collected": records_collected,
            "unique_dois": unique_dois,
            "pagination_complete": records_collected == size_records,
            "dois_unique": unique_dois == records_collected,
            "failed_pages": failed_pages,
        },
        "violations": violations,
        "n_violations": len(violations),
        "allowed_violations": int(
            prereg["pre_registered_criteria"]["A_catalog_integrity_and_pagination"][
                "allowed_violations"
            ]
        ),
        "passed": not violations,
    }


def evaluate_criterion_b(
    value_layer: Mapping[str, Any],
    table_rows: Sequence[Mapping[str, str]],
    raw_rows: Sequence[Mapping[str, str]],
    prereg: Mapping[str, Any],
) -> dict[str, Any]:
    ledger = dict(value_layer["ledger"])
    accepted = int(ledger.get("accepted_pure_rows", 0))
    rejected = (
        int(ledger.get("unit_rejected", 0))
        + int(ledger.get("temperature_rejected", 0))
        + int(ledger.get("value_rejected", 0))
    )
    multi = int(value_layer["multi_component_density_rows"])
    total_named = int(value_layer["total_named_density_rows"])

    violations: list[str] = []
    if accepted + rejected + multi != total_named:
        violations.append(
            f"拒绝账本不平：accepted({accepted}) + rejected({rejected}) + multi({multi}) "
            f"!= 命中属性名总行({total_named})"
        )
    if accepted != len(table_rows):
        violations.append(
            f"主表行数 {len(table_rows)} 与账本 accepted {accepted} 不符"
        )

    accepted_raw = [row for row in raw_rows if row.get("quality_flag") == "accepted"]
    if len(accepted_raw) != int(ledger.get("accepted_pure_rows", 0)):
        violations.append(
            f"原始层 accepted 行数 {len(accepted_raw)} 与账本 accepted "
            f"{int(ledger.get('accepted_pure_rows', 0))} 不符"
        )

    invalid: list[dict[str, str]] = []
    for index, row in enumerate(accepted_raw):
        reason = ""
        if row["property_name"].strip().lower() not in ACCEPTED_PROPERTY_NAMES:
            reason = "property_name_not_accepted"
        elif row["property_unit_raw"] not in UNIT_TO_KG_M3:
            reason = "unit_not_in_table"
        else:
            temperature = to_float(row["T_K"])
            density = to_float(row["density_kg_m3"])
            if temperature is None or not (MIN_T_K < temperature < MAX_T_K):
                reason = "temperature_out_of_range"
            elif density is None or not (MIN_RHO_KG_M3 < density < MAX_RHO_KG_M3):
                reason = "density_out_of_range"
        if reason:
            invalid.append({"index": str(index), "reason": reason})
    if invalid:
        violations.append(f"主表有 {len(invalid)} 行不满足取值契约")

    return {
        "id": "B",
        "ledger": ledger,
        "multi_component_density_rows": multi,
        "total_named_density_rows": total_named,
        "table_rows": len(table_rows),
        "unit_table_entries": len(UNIT_TO_KG_M3),
        "invalid_rows": invalid[:20],
        "invalid_row_count": len(invalid),
        "parse_failures": list(value_layer.get("parse_failures", [])),
        "violations": violations,
        "n_violations": len(violations),
        "allowed_violations": int(
            prereg["pre_registered_criteria"]["B_value_extraction_integrity"][
                "allowed_violations"
            ]
        ),
        "passed": not violations,
    }


def evaluate_criterion_c(
    pairing: Mapping[str, Any], prereg: Mapping[str, Any]
) -> dict[str, Any]:
    expected_rows = int(prereg["frozen_expectations"]["local_kinematic_rows"])
    per_row = list(pairing["per_row"])
    violations: list[str] = []
    if len(per_row) != expected_rows:
        violations.append(
            f"本地运动黏度逐行判定 {len(per_row)} 条 vs 预注册 {expected_rows} 行"
        )
    recomputed_exact = sum(1 for entry in per_row if entry["exact"])
    recomputed_nearest = sum(1 for entry in per_row if entry["nearest"])
    if recomputed_exact != int(pairing["exact_rows"]):
        violations.append("exact 行数与逐行重算不一致")
    if recomputed_nearest != int(pairing["nearest_rows"]):
        violations.append("nearest 行数与逐行重算不一致")
    missing_trace = [
        entry["inchikey"]
        for entry in per_row
        if entry["nearest"]
        and not (
            entry["nearest_source_doi"]
            and entry["nearest_thermoml_file"]
            and entry["nearest_source_row_index"]
        )
    ]
    if missing_trace:
        violations.append(f"配对行缺来源三元组：{missing_trace[:5]}（共 {len(missing_trace)}）")

    return {
        "id": "C",
        "local_rows": len(per_row),
        "local_keys": int(pairing["local_keys"]),
        "exact_rows": int(pairing["exact_rows"]),
        "unfreeze_rows": int(pairing["nearest_rows"]),
        "exact_tolerance_k": float(pairing["exact_tolerance_k"]),
        "nearest_tolerance_k": float(pairing["nearest_tolerance_k"]),
        "by_key": dict(pairing["by_key"]),
        "per_row": [dict(entry) for entry in pairing["per_row"]],
        "violations": violations,
        "n_violations": len(violations),
        "allowed_violations": int(
            prereg["pre_registered_criteria"]["C_unfreeze_metric"]["allowed_violations"]
        ),
        "passed": not violations,
    }


def evaluate_criterion_d(
    dataset: Mapping[str, Any],
    value_layer: Mapping[str, Any],
    prereg: Mapping[str, Any],
) -> dict[str, Any]:
    slice_dataset = dataset["slice"]
    machine = prereg["pre_registered_criteria"]["D_basis_honesty"]["machine_readable"]
    violations: list[str] = []
    required = {
        "size_unit": "record",
        "online_row_count": "unknown",
        "value_basis": "thermoml_xml_observation_row",
        "must_report_phrase_vs_structured": True,
        "row_comparison_allowed": False,
    }
    for key, value in required.items():
        if machine.get(key) != value:
            violations.append(f"预注册 D 的机读字段 {key} 不是 {value}")
    phrase_vs_structured = {
        "query": DENSITY_QUERY,
        "size_records": int(slice_dataset["size_records"]),
        "records_with_mass_density_name": int(slice_dataset["records_with_mass_density_name"]),
        "records_with_critical_density_name": int(
            slice_dataset["records_with_critical_density_name"]
        ),
        "statement": "检索词走短语索引：命中的记录里，结构化 ePropName 恰为 Mass density, kg/m3 与恰为 "
        "Critical density, kg/m3 的分别计数；两者都不是本表要的口径，主表只取 Mass density, kg/m3 的纯组分行。",
    }
    if not phrase_vs_structured["records_with_mass_density_name"]:
        violations.append("没有报出结构化 Mass density, kg/m3 命中的记录数")
    return {
        "id": "D",
        "size_unit": "record",
        "size_unit_statement": "在线目录层的 size 是检索命中的 ThermoML 记录（文档）数，不是数据行数；"
        "它不能与本表（或任何 CSV）的观测行数相减或相除。",
        "online_row_count": "unknown",
        "online_row_count_reason": "JSON API 只暴露记录级元数据与 data_summary 计数，不含 NumValues 数值行"
        "（跑前侦察实测：整页 100 条记录里 nValue/PropertyValue 均出现 0 次），故在线行数只能记 unknown，不估。",
        "value_basis": "thermoml_xml_observation_row",
        "value_basis_statement": "本表的每一行都来自同一 DOI 的 ThermoML XML 的一个 NumValues 行，"
        "与在线记录数是两套口径，禁止相除当覆盖率。",
        "phrase_index_vs_structured_property": phrase_vs_structured,
        "row_comparison_allowed": False,
        "violations": violations,
        "n_violations": len(violations),
        "allowed_violations": int(
            prereg["pre_registered_criteria"]["D_basis_honesty"]["allowed_violations"]
        ),
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
                violations.append(f"第 {index} 行含未加限定的 {token}：{line.strip()[:90]}")
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
# CSV 文本 / summary / report
# --------------------------------------------------------------------------------------


def csv_text(fieldnames: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> str:
    import io

    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer, fieldnames=list(fieldnames), lineterminator="\n", extrasaction="ignore"
    )
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def catalog_manifest(slice_dataset: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "query": slice_dataset["query"],
        "page_size": int(slice_dataset["page_size"]),
        "size_records": int(slice_dataset["size_records"]),
        "pages_fetched": int(slice_dataset["pages_fetched"]),
        "records_collected": int(slice_dataset["records_collected"]),
        "unique_dois": int(slice_dataset["unique_dois"]),
        "records_with_mass_density_name": int(slice_dataset["records_with_mass_density_name"]),
        "records_with_critical_density_name": int(
            slice_dataset["records_with_critical_density_name"]
        ),
        "records_with_pure_mass_density": int(slice_dataset["records_with_pure_mass_density"]),
        "dois": list(slice_dataset["dois"]),
        "dois_with_pure_mass_density": list(slice_dataset["dois_with_pure_mass_density"]),
        "compound_keys": list(slice_dataset["compound_keys"]),
    }


def build_summary(
    *,
    prereg: Mapping[str, Any],
    prereg_path: Path,
    prereg_sha256: str,
    dataset: Mapping[str, Any],
    value_layer: Mapping[str, Any],
    table_rows: Sequence[Mapping[str, str]],
    raw_rows: Sequence[Mapping[str, str]],
    coverage: Mapping[str, Any],
    pairing: Mapping[str, Any],
    kinematic: Mapping[str, Any],
    input_digests: Mapping[str, Any],
    outputs: Mapping[str, Any],
    run_provenance: Mapping[str, Any],
    generated_at: str,
) -> dict[str, Any]:
    criterion_a = evaluate_criterion_a(dataset, prereg)
    criterion_b = evaluate_criterion_b(value_layer, table_rows, raw_rows, prereg)
    criterion_c = evaluate_criterion_c(pairing, prereg)
    criterion_d = evaluate_criterion_d(dataset, value_layer, prereg)

    manifest = catalog_manifest(dataset["slice"])
    unique_keys = sorted({row["inchikey"] for row in table_rows if row["inchikey"]})
    findings = [
        (
            "目录层：检索词 * 的在线 size 是 {} 条记录，检索词 \"Density, kg/m3\" 的在线 size 是 "
            "{} 条记录，分 {} 页从 pageNum=0 抓全（抓到 {} 条记录，DOI 唯一 {} 个）。"
        ).format(
            dataset["total_records"]["size_records"],
            dataset["slice"]["size_records"],
            dataset["slice"]["pages_fetched"],
            dataset["slice"]["records_collected"],
            dataset["slice"]["unique_dois"],
        ),
        (
            "目录层里结构化 ePropName 恰为 Mass density, kg/m3 的记录 {} 条、恰为 Critical density, "
            "kg/m3 的记录 {} 条：检索词是短语索引，不能拿 size 当「全是 ρ(T)」。"
        ).format(
            dataset["slice"]["records_with_mass_density_name"],
            dataset["slice"]["records_with_critical_density_name"],
        ),
        (
            "数值层：从目录层里 {} 条含纯组分 Mass density, kg/m3 的记录的 ThermoML XML 里抽出密度观测行，"
            "其中纯组分接受 {} 行、拒绝 {} 行、多组分行 {} 行。"
        ).format(
            dataset["slice"]["records_with_pure_mass_density"],
            criterion_b["ledger"].get("accepted_pure_rows", 0),
            criterion_b["ledger"].get("unit_rejected", 0)
            + criterion_b["ledger"].get("temperature_rejected", 0)
            + criterion_b["ledger"].get("value_rejected", 0),
            criterion_b["multi_component_density_rows"],
        ),
        (
            "解冻指标：本地运动黏度 {} 行（{} 个化合物）里，exact 温度配到密度的 {} 行，"
            "nearest（|ΔT| <= {} K）{} 行。"
        ).format(
            pairing["local_rows"],
            pairing["local_keys"],
            pairing["exact_rows"],
            pairing["nearest_tolerance_k"],
            pairing["nearest_rows"],
        ),
        (
            "覆盖率（口径：化合物，唯一 InChIKey）：vs dielectric_v03 {} / {}，vs identity_map {} / {}，"
            "vs 本地运动黏度化合物 {} / {}。"
        ).format(
            coverage["vs_dielectric_v03"]["intersection_size"],
            coverage["vs_dielectric_v03"]["target_size"],
            coverage["vs_identity_map"]["intersection_size"],
            coverage["vs_identity_map"]["target_size"],
            coverage["vs_local_kinematic"]["intersection_size"],
            coverage["vs_local_kinematic"]["target_size"],
        ),
    ]
    limitations = [
        (
            "在线目录层的 size 是记录数，不是数据行数；在线行数记 unknown（JSON API 不含数值行），"
            "本表不给出任何以在线记录数为分母的行口径覆盖率。"
        ),
        (
            "本表的行是 ThermoML XML 的 NumValues 观测行，与目录层记录数是两套口径；XML 数值层来自 "
            + XML_BASE
            + "/{doi}.xml，与目录层同源同 DOI，但不是同一份字节。"
        ),
        (
            "覆盖率的单位一律是化合物（唯一 InChIKey），不是观测行、不是记录；缺的键逐条列在 "
            "summary 的 coverage 一节。"
        ),
        (
            "只取 Mass density, kg/m3（含别名 Density, kg/m3）的纯组分行；Critical density, kg/m3、"
            "Amount density, mol/m3、多组分行都不入主表，只在 summary 里计数。"
        ),
        (
            "解冻指标只做「同 InChIKey + 同温度（exact）或最近邻且 |ΔT| <= 1.0 K」的配对，"
            "不插值、不外推；1.0 K 之外没有密度就记未配对。"
        ),
        "本臂只建表与计数：不拟合模型、不产 R2/MAE、不改任何既有文件。",
    ]
    return {
        "schema_version": 1,
        "task": "build_density_v01",
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
            "xml_base": XML_BASE,
            "user_agent": USER_AGENT,
            "page_size": PAGE_SIZE,
            "throttle_seconds": THROTTLE_SECONDS,
            "total_records_query": TOTAL_RECORDS_QUERY,
            "page_num_base": FIRST_PAGE_NUM,
            "pagination_note": "pageNum 是 0 基的，窗口为 [pageNum * pageSize, (pageNum + 1) * pageSize)；"
            "从 pageNum=1 起分页会永久漏掉最前 pageSize 条。",
            "proxy_mode": "direct（ProxyHandler({})；本机环境代理指向失效端口）",
        },
        "inputs": dict(input_digests),
        "dataset": {
            "total_records": dict(dataset["total_records"]),
            "slice": dict(dataset["slice"]),
            "manifest": manifest,
            "manifest_sha256": sha256_text(canonical_json(manifest)),
        },
        "value_layer": {
            "total_named_density_rows": int(value_layer["total_named_density_rows"]),
            "multi_component_density_rows": int(value_layer["multi_component_density_rows"]),
            "ledger": dict(value_layer["ledger"]),
            "parse_failures": list(value_layer.get("parse_failures", [])),
            "smiles_unresolved": int(value_layer.get("smiles_unresolved", 0)),
            "unique_keys": len(unique_keys),
            "temperature_distribution": temperature_distribution(table_rows),
        },
        "coverage": dict(coverage),
        "criterion_a_catalog": criterion_a,
        "criterion_b_values": criterion_b,
        "criterion_c_unfreeze": criterion_c,
        "criterion_d_honesty": criterion_d,
        "outputs": dict(outputs),
        "run_provenance": dict(run_provenance),
        "findings": findings,
        "limitations": limitations,
    }


def render_report(summary: Mapping[str, Any]) -> str:
    lines: list[str] = []
    add = lines.append
    criterion_a = summary["criterion_a_catalog"]
    criterion_b = summary["criterion_b_values"]
    criterion_c = summary["criterion_c_unfreeze"]
    criterion_d = summary["criterion_d_honesty"]
    slice_dataset = summary["dataset"]["slice"]
    value_layer = summary["value_layer"]
    pairing = summary["criterion_c_unfreeze"]

    add("# W17-4 加维度①·密度 ρ(T)：density_v01 纯组分密度表")
    add("")
    add("- 探针：probes/build_density_v01.py")
    add(
        "- 预注册（跑前冻结）：{}，sha256 {}，locked_at_utc {}，status {}".format(
            summary["prereg"]["path"],
            summary["prereg"]["sha256"],
            summary["prereg"]["locked_at_utc"],
            summary["prereg"]["status"],
        )
    )
    add("- 机读汇总：probes/density_v01_summary.json")
    add(
        "- 新表：{}（{} 条纯组分密度观测）；原始层：{}".format(
            summary["outputs"]["table"]["path"],
            summary["outputs"]["table"]["rows"],
            summary["outputs"]["raw"]["path"],
        )
    )
    add(
        "- 数据源两层：目录层 = NIST/TRC ThermoML 检索 API；数值层 = 同源 ThermoML XML（{}）".format(
            summary["api"]["xml_base"]
        )
    )
    add("- 建模：无。六件冻结件：未动。本臂不修改任何既有文件。")
    add("")
    add("## 1 目录层读数（口径：记录数，不是数据行数）")
    add("")
    add("| 检索词 | 在线 size（记录数） | 已抓记录数 | 页数 |")
    add("|---|---:|---:|---:|")
    add(
        "| {} | {} 条记录 | — | 1 |".format(
            summary["dataset"]["total_records"]["query"],
            summary["dataset"]["total_records"]["size_records"],
        )
    )
    add(
        "| {} | {} 条记录 | {} | {} |".format(
            slice_dataset["query"],
            slice_dataset["size_records"],
            slice_dataset["records_collected"],
            slice_dataset["pages_fetched"],
        )
    )
    add("")
    add(
        "- 结构化 ePropName 命中（按记录计）：Mass density, kg/m3 {} 条记录；Critical density, kg/m3 "
        "{} 条记录。检索词是短语索引，故 size 记录数不等于「全是 ρ(T)」.".format(
            slice_dataset["records_with_mass_density_name"],
            slice_dataset["records_with_critical_density_name"],
        )
    )
    add(
        "- 判据 A：{} 条违反，允许 {}，判 {}。".format(
            criterion_a["n_violations"],
            criterion_a["allowed_violations"],
            "通过" if criterion_a["passed"] else "未通过",
        )
    )
    add("")
    add("## 2 数值层（ThermoML XML 观测行）")
    add("")
    add(
        "- 目录层里含纯组分 Mass density, kg/m3 的记录 {} 条；这些记录的 ThermoML XML 构成数值层。".format(
            slice_dataset["records_with_pure_mass_density"]
        )
    )
    add(
        "- 命中 accepted 属性名的总观测：{} 条；其中纯组分接受 {} 条、拒绝 {} 条、多组分 {} 条。".format(
            value_layer["total_named_density_rows"],
            criterion_b["ledger"].get("accepted_pure_rows", 0),
            criterion_b["ledger"].get("unit_rejected", 0)
            + criterion_b["ledger"].get("temperature_rejected", 0)
            + criterion_b["ledger"].get("value_rejected", 0),
            value_layer["multi_component_density_rows"],
        )
    )
    add(
        "- 唯一 InChIKey 数：{}；smiles 未能还原的行数：{}。".format(
            value_layer["unique_keys"], value_layer["smiles_unresolved"]
        )
    )
    add(
        "- 判据 B：{} 条违反，允许 {}，判 {}。".format(
            criterion_b["n_violations"],
            criterion_b["allowed_violations"],
            "通过" if criterion_b["passed"] else "未通过",
        )
    )
    add("")
    add("| 温度区间 | 观测行数 |")
    add("|---|---:|")
    for entry in value_layer["temperature_distribution"]:
        add("| {} | {} |".format(entry["label"], entry["count"]))
    add("")
    add("## 3 覆盖率（口径：化合物，唯一 InChIKey）")
    add("")
    add("| 目标集合 | 目标键数 | 密度表键数 | 交集 | 覆盖率 | 缺失键 |")
    add("|---|---:|---:|---:|---:|---:|")
    for block_id in ("vs_dielectric_v03", "vs_identity_map", "vs_local_kinematic"):
        block = summary["coverage"][block_id]
        fraction = block["covered_fraction"]
        add(
            "| {} | {} | {} | {} | {} | {} |".format(
                block_id,
                block["target_size"],
                block["density_size"],
                block["intersection_size"],
                "—" if fraction is None else f"{float(fraction):.4f}",
                len(block["missing_keys"]),
            )
        )
    add("")
    add("缺失键清单逐条列在 probes/density_v01_summary.json 的 coverage 一节。")
    add("")
    add("## 4 解冻指标（判据 C）")
    add("")
    add("- 目标：本地运动黏度 {} 行（{} 个化合物）。".format(pairing["local_rows"], pairing["local_keys"]))
    add(
        "- exact（|ΔT| <= {} K）配到密度：{} 行。".format(
            pairing["exact_tolerance_k"], pairing["exact_rows"]
        )
    )
    add(
        "- nearest（|ΔT| <= {} K，取最近邻）配到密度 = 解冻行数：{} 行。".format(
            pairing["nearest_tolerance_k"], pairing["unfreeze_rows"]
        )
    )
    add(
        "- 判据 C：{} 条违反，允许 {}，判 {}。".format(
            criterion_c["n_violations"],
            criterion_c["allowed_violations"],
            "通过" if criterion_c["passed"] else "未通过",
        )
    )
    add("")
    add("| InChIKey | 运动黏度行数 | exact | nearest |")
    add("|---|---:|---:|---:|")
    for key, bucket in summary["criterion_c_unfreeze"]["by_key"].items():
        add("| {} | {} | {} | {} |".format(key, bucket["rows"], bucket["exact"], bucket["nearest"]))
    add("")
    add("## 5 口径诚实性（判据 D）")
    add("")
    add("- " + criterion_d["size_unit_statement"])
    add("- 在线数据行数：unknown —— " + criterion_d["online_row_count_reason"])
    add("- " + criterion_d["value_basis_statement"])
    add(
        "- 短语命中 vs 结构化命中：{} 条记录里，结构化 Mass density, kg/m3 {} 条记录、"
        "Critical density, kg/m3 {} 条记录。".format(
            slice_dataset["size_records"],
            slice_dataset["records_with_mass_density_name"],
            slice_dataset["records_with_critical_density_name"],
        )
    )
    add(
        "- 判据 D：{} 条违反，允许 {}，判 {}。".format(
            criterion_d["n_violations"],
            criterion_d["allowed_violations"],
            "通过" if criterion_d["passed"] else "未通过",
        )
    )
    add("")
    add("## 6 读数与边界")
    add("")
    for item in summary["findings"]:
        add("- " + str(item))
    for item in summary["limitations"]:
        add("- " + str(item))
    add("")
    add("## 7 复现")
    add("")
    add("- 首跑：.venv\\Scripts\\python.exe probes/build_density_v01.py --resolve-online")
    add("- 增量：.venv\\Scripts\\python.exe probes/build_density_v01.py")
    add("- 离线核查：.venv\\Scripts\\python.exe probes/build_density_v01.py --check")
    add("- 独立核验：.venv\\Scripts\\python.exe scripts/verify_density_v01.py --check")
    add("- 目录层清单指纹（manifest_sha256）：" + str(summary["dataset"]["manifest_sha256"]))
    add("")
    return "\n".join(lines)


# --------------------------------------------------------------------------------------
# 运行入口
# --------------------------------------------------------------------------------------


def compose(
    args: argparse.Namespace,
    *,
    online: bool,
    refresh: bool,
    generated_at: str | None,
    fallback_summary: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], str, list[dict[str, str]], list[dict[str, str]]]:
    prereg = json.loads(args.prereg.read_text(encoding="utf-8"))
    prereg_sha256 = sha256_file(args.prereg)

    kinematic_all = read_csv_rows(args.kinematic)
    kinematic_rows = [
        row
        for row in kinematic_all
        if (row.get("property_name") or "").strip() == KINEMATIC_PROPERTY
    ]
    kinematic_keys = {
        (row.get("inchikey") or "").strip()
        for row in kinematic_rows
        if (row.get("inchikey") or "").strip()
    }

    input_digests = {
        "kinematic": {
            "path": display_path(args.kinematic),
            "sha256": sha256_file(args.kinematic),
            "rows": len(kinematic_rows),
            "keys": len(kinematic_keys),
        },
        "dielectric_v03": {
            "path": display_path(args.dielectric),
            "sha256": sha256_file(args.dielectric),
            "keys": len(read_keys(args.dielectric, "inchikey")),
        },
        "identity_map": {
            "path": display_path(args.identity_map),
            "sha256": sha256_file(args.identity_map),
            "keys": len(read_keys(args.identity_map, "inchikey")),
        },
    }

    fallback = fallback_summary
    if fallback is None and args.summary.is_file():
        fallback = json.loads(args.summary.read_text(encoding="utf-8"))

    budget = RequestBudget(limit=int(prereg["api"]["request_budget_limit"]))
    ledger: list[dict[str, Any]] = []

    try:
        dataset: dict[str, Any] = collect_catalog(
            cache_dir=args.catalog_cache,
            online=online,
            refresh=refresh,
            http_get=default_http_get,
            budget=budget,
            ledger=ledger,
        )
        catalog_status = {
            "dataset_source": "network_plus_cache" if online else "raw_api_cache",
            "catalog_cache_dir": display_path(args.catalog_cache),
            "reason": "目录层从原始响应字节重算。",
        }
    except CacheMiss:
        if fallback is None:
            raise
        dataset = {
            "total_records": dict(fallback["dataset"]["total_records"]),
            "slice": dict(fallback["dataset"]["slice"]),
            "sources": [],
        }
        catalog_status = {
            "dataset_source": "committed_summary",
            "catalog_cache_dir": display_path(args.catalog_cache),
            "reason": "目录层原始响应缓存缺失（data/external/thermoml_api/ 被 .gitignore 忽略），"
            "离线复算改用已提交 summary 的目录层清单。",
        }

    page_sources = list(dataset.pop("sources", []))
    value_layer: dict[str, Any] | None = None
    xml_status: dict[str, Any] = {}
    dois = list(dataset["slice"].get("dois_with_pure_mass_density", []))
    if dois:
        xml_results, xml_status = download_xmls(
            dois,
            cache_dir=args.xml_cache,
            online=online,
            refresh=refresh,
            http_get=default_http_get,
            budget=budget,
            ledger=ledger,
        )
        if xml_status["available"] > 0:
            value_layer = extract_value_layer(xml_results)
    if value_layer is None:
        if fallback is None or not (args.raw.is_file() and args.table.is_file()):
            raise ValueLayerUnavailable(
                "数值层 XML 缓存缺失，且没有可退用的已提交产物（data/processed/density_raw.csv）。"
            )
        value_layer = {
            "source": "committed_csv",
            "raw_rows": read_csv_rows(args.raw),
            "total_named_density_rows": int(fallback["value_layer"]["total_named_density_rows"]),
            "multi_component_density_rows": int(
                fallback["value_layer"]["multi_component_density_rows"]
            ),
            "parse_failures": list(fallback["value_layer"].get("parse_failures", [])),
            "smiles_unresolved": int(fallback["value_layer"].get("smiles_unresolved", 0)),
        }
    value_layer["xml_status"] = xml_status
    value_layer["ledger"] = ledger_from_raw(value_layer["raw_rows"])

    table_rows = table_rows_from_raw(value_layer["raw_rows"])
    raw_for_csv = [
        {column: row.get(column, "") for column in RAW_COLUMNS} for row in value_layer["raw_rows"]
    ]
    density_keys = {row["inchikey"] for row in table_rows if row["inchikey"]}

    coverage = {
        "vs_dielectric_v03": coverage_block(
            "vs_dielectric_v03", args.dielectric, read_keys(args.dielectric, "inchikey"), density_keys
        ),
        "vs_identity_map": coverage_block(
            "vs_identity_map", args.identity_map, read_keys(args.identity_map, "inchikey"), density_keys
        ),
        "vs_local_kinematic": coverage_block(
            "vs_local_kinematic", args.kinematic, kinematic_keys, density_keys
        ),
    }
    pairing = pair_kinematic_rows(kinematic_rows, table_rows)

    outputs = {
        "table": {
            "path": display_path(args.table),
            "rows": len(table_rows),
            "columns": list(TABLE_COLUMNS),
            "sha256": sha256_text(csv_text(TABLE_COLUMNS, table_rows)),
            "unit": "kg/m3",
        },
        "raw": {
            "path": display_path(args.raw),
            "rows": len(raw_for_csv),
            "columns": list(RAW_COLUMNS),
            "sha256": sha256_text(csv_text(RAW_COLUMNS, raw_for_csv)),
        },
    }

    run_mode = "refresh" if (online and refresh) else ("incremental" if online else "offline")
    network_calls = sum(1 for entry in ledger if entry.get("source") == "network")
    cache_hits = sum(1 for entry in ledger if entry.get("source") == "local_cache")
    run_provenance = {
        "run_mode": run_mode,
        "run_telemetry": {
            "network_calls": network_calls,
            "cache_hits": cache_hits,
            "models_fitted": 0,
            "r2_reported": 0,
            "writes_under_data": 2,
            "run_mode": run_mode,
            "writes_under_data_note": "新增并写入 data/ 的版本库产物：data/density_v01.csv 与 "
            "data/processed/density_raw.csv；原始缓存写在 data/external/ 与 data/raw/ 下。",
        },
        "requests": {
            "budget_limit": budget.limit,
            "requests_spent": budget.used,
            "bytes_transferred": budget.bytes_transferred,
            "ledger": ledger,
        },
        "cache": dict(catalog_status),
        "catalog_page_sources": page_sources,
        "value_layer_source": str(value_layer.get("source", "")),
        "xml_status": dict(xml_status),
        "xml_cache_dir": display_path(args.xml_cache),
    }

    summary = build_summary(
        prereg=prereg,
        prereg_path=args.prereg,
        prereg_sha256=prereg_sha256,
        dataset=dataset,
        value_layer=value_layer,
        table_rows=table_rows,
        raw_rows=raw_for_csv,
        coverage=coverage,
        pairing=pairing,
        kinematic={"rows": len(kinematic_rows), "keys": len(kinematic_keys)},
        input_digests=input_digests,
        outputs=outputs,
        run_provenance=run_provenance,
        generated_at=generated_at or utc_now(),
    )
    report = render_report(summary)
    violations = guard_violations(prereg, report, summary)
    if violations:
        raise RuntimeError("口径守卫不通过：" + "；".join(violations))
    return summary, report, table_rows, raw_for_csv


def print_summary(
    summary: Mapping[str, Any], summary_path: Path, report_path: Path
) -> None:
    criterion_a = summary["criterion_a_catalog"]
    criterion_b = summary["criterion_b_values"]
    criterion_c = summary["criterion_c_unfreeze"]
    criterion_d = summary["criterion_d_honesty"]
    slice_dataset = summary["dataset"]["slice"]
    print("prereg sha256 : {}".format(summary["prereg"]["sha256"]))
    print("catalog source: {}".format(summary["run_provenance"]["cache"]["dataset_source"]))
    print(
        "catalog       : *={} 记录, density={} 记录, pages={}, collected={}, unique_dois={}".format(
            summary["dataset"]["total_records"]["size_records"],
            slice_dataset["size_records"],
            slice_dataset["pages_fetched"],
            slice_dataset["records_collected"],
            slice_dataset["unique_dois"],
        )
    )
    xml_status = summary["run_provenance"]["xml_status"]
    print(
        "value layer   : {} (xml available {}/{}, failed {})".format(
            summary["run_provenance"]["value_layer_source"],
            xml_status.get("available", 0),
            xml_status.get("requested", 0),
            xml_status.get("failed", 0),
        )
    )
    print(
        "density table : {} 条纯组分观测, {} 唯一键".format(
            summary["outputs"]["table"]["rows"], summary["value_layer"]["unique_keys"]
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
        "criterion B   : {} (violations {}/{})".format(
            "PASS" if criterion_b["passed"] else "FAIL",
            criterion_b["n_violations"],
            criterion_b["allowed_violations"],
        )
    )
    print(
        "criterion C   : {} (exact {}, unfreeze {}, of {} local rows)".format(
            "PASS" if criterion_c["passed"] else "FAIL",
            criterion_c["exact_rows"],
            criterion_c["unfreeze_rows"],
            criterion_c["local_rows"],
        )
    )
    print(
        "criterion D   : {} (violations {}/{})".format(
            "PASS" if criterion_d["passed"] else "FAIL",
            criterion_d["n_violations"],
            criterion_d["allowed_violations"],
        )
    )
    print("manifest sha  : {}".format(summary["dataset"]["manifest_sha256"]))
    print(f"summary       : {display_path(summary_path)}")
    print(f"report        : {display_path(report_path)}")


def read_text_raw(path: Path) -> str:
    with path.open(encoding="utf-8", newline="") as handle:
        return handle.read()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="W17-4 密度 rho(T) 建表（NIST/TRC ThermoML 目录层 + XML 数值层）。"
    )
    parser.add_argument("--resolve-online", action="store_true", help="首跑：联网抓目录层与数值层")
    parser.add_argument("--refresh", action="store_true", help="忽略原始缓存，强制重新联网")
    parser.add_argument("--check", action="store_true", help="离线重算并与磁盘产物比对")
    parser.add_argument("--prereg", type=Path, default=DEFAULT_PREREG)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--catalog-cache", type=Path, default=DEFAULT_CATALOG_CACHE)
    parser.add_argument("--xml-cache", type=Path, default=DEFAULT_XML_CACHE)
    parser.add_argument("--table", type=Path, default=DEFAULT_TABLE)
    parser.add_argument("--raw", type=Path, default=DEFAULT_RAW)
    parser.add_argument("--dielectric", type=Path, default=DEFAULT_DIELECTRIC)
    parser.add_argument("--identity-map", type=Path, default=DEFAULT_IDENTITY_MAP)
    parser.add_argument("--kinematic", type=Path, default=DEFAULT_KINEMATIC)
    args = parser.parse_args(argv)

    online = bool(args.resolve_online) and not args.check
    refresh = bool(args.refresh) and online

    if args.check:
        if not args.summary.is_file():
            print(f"FAIL 缺 summary：{display_path(args.summary)}")
            return 1
        disk = json.loads(args.summary.read_text(encoding="utf-8"))
        summary, report, table_rows, raw_rows = compose(
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
        elif read_text_raw(args.report) != report:
            problems.append("report 不是 render_report(summary) 的逐字输出")
        if not args.table.is_file():
            problems.append(f"缺表：{display_path(args.table)}")
        elif read_text_raw(args.table) != csv_text(TABLE_COLUMNS, table_rows):
            problems.append("density_v01.csv 与离线重算不一致")
        if not args.raw.is_file():
            problems.append(f"缺原始层：{display_path(args.raw)}")
        elif read_text_raw(args.raw) != csv_text(RAW_COLUMNS, raw_rows):
            problems.append("density_raw.csv 与离线重算不一致")
        for problem in problems:
            print("FAIL " + problem)
        if problems:
            return 1
        criterion_a = summary["criterion_a_catalog"]
        criterion_c = summary["criterion_c_unfreeze"]
        print(
            "OK 离线复算一致；判据 A {}；解冻 {}/{} 行；目录层来源 {}；数值层来源 {}".format(
                "PASS" if criterion_a["passed"] else "FAIL",
                criterion_c["unfreeze_rows"],
                criterion_c["local_rows"],
                summary["run_provenance"]["cache"]["dataset_source"],
                summary["run_provenance"]["value_layer_source"],
            )
        )
        return 0

    summary, report, table_rows, raw_rows = compose(
        args, online=online, refresh=refresh, generated_at=None
    )
    write_json_lf(args.summary, summary)
    write_text_lf(args.report, report)
    write_csv_lf(args.table, TABLE_COLUMNS, table_rows)
    write_csv_lf(args.raw, RAW_COLUMNS, raw_rows)
    print_summary(summary, args.summary, args.report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
