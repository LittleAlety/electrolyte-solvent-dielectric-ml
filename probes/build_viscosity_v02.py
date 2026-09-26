r"""W17-3 扩物质·在线黏度切片入库：把 NIST/TRC ThermoML 的黏度观测建成 viscosity_v02 新表。

三层结构（与 W17-4 密度臂同源同纪律）：
  目录层：/ThermoML-API/objects 这个 JSON 检索 API。三条检索词：
    * 的全库 size 记录数、\"Viscosity, Pa*s\" 切片、\"Kinematic viscosity, m2/s\" 切片。
    该 API 的 pageNum 是 0 基的：窗口 [pageNum * pageSize, (pageNum + 1) * pageSize)。
  数值层：同源的 ThermoML XML（https://trc.nist.gov/ThermoML/{doi}.xml）。
    侦察实测：JSON API 只带 Citation / Compound / PureOrMixtureData 的定义与 data_summary 计数，
    整页记录里 \"nValue\"/\"PropertyValue\" 均出现 0 次。所以黏度数值只能从 XML 取——本探针把
    这条口径写进 summary，不假装 JSON API 里有观测行。
  解冻层：本地 176 行运动黏度 kappa(T) 用 data/density_v01.csv 的 rho(T) 反解 eta = kappa * rho。

四件判据在跑之前冻结在 probes/build_viscosity_v02_prereg.json 里：
  A 目录层逐位复现（* 11923 条记录 / Pa*s 切片 1690 条记录 / kinematic 切片 70 条记录，
    两个切片都按 pageSize=100 从 pageNum=0 抓全，DOI 唯一，零失败页）；
  B 本地 29 个含黏度 DOI 全部命中所抓在线清单；
  C 单位诚实三档（单位换算表显式列全，未识别单位 / 超范围温度 / 非法值各自进 ledger，不静默丢）；
  D 诚实边界（size 是记录数不是物质数；记录数 / InChIKey 数两个口径分开报；多组分另册登记）。

不做：不拟合任何模型、不产 R2/MAE、不改任何既有文件、不把任何值写进六件冻结件。

用法（PowerShell，仓库根）：
    .\.venv\Scripts\python.exe probes/build_viscosity_v02.py --resolve-online   # 首跑：联网
    .\.venv\Scripts\python.exe probes/build_viscosity_v02.py                    # 增量：缓存已有的不再联网
    .\.venv\Scripts\python.exe probes/build_viscosity_v02.py --check            # 离线重算并与磁盘产物比对
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

PA_S_QUERY = '"Viscosity, Pa*s"'
PA_S_SLUG = "viscosity_pa_s"
PA_S_PROPERTY = "Viscosity, Pa*s"

KINEMATIC_QUERY = '"Kinematic viscosity, m2/s"'
KINEMATIC_SLUG = "kinematic_viscosity"
KINEMATIC_PROPERTY = "Kinematic viscosity, m2/s"

# 单位诚实三档的第一档：显式换算表。不在表里的单位一律进 unit_rejected 账本，不静默丢。
PA_S_UNIT_TO_PA_S: dict[str, float] = {
    "Pa*s": 1.0,
    "Pa s": 1.0,
    "Pa.s": 1.0,
    "Pas": 1.0,
    "N*s/m2": 1.0,
    "N.s/m2": 1.0,
    "kg/(m*s)": 1.0,
    "kg/(m.s)": 1.0,
    "mPa*s": 1e-3,
    "mPa.s": 1e-3,
    "mPa s": 1e-3,
    "uPa*s": 1e-6,
    "\u00b5Pa*s": 1e-6,
    "\u03bcPa*s": 1e-6,
    "cP": 1e-3,
    "centipoise": 1e-3,
    "P": 0.1,
    "poise": 0.1,
}

KINEMATIC_UNIT_TO_M2_S: dict[str, float] = {
    "m2/s": 1.0,
    "m^2/s": 1.0,
    "m2 s-1": 1.0,
    "m2.s-1": 1.0,
    "mm2/s": 1e-6,
    "cm2/s": 1e-4,
    "cSt": 1e-6,
    "St": 1e-4,
}

ACCEPTED_PROPERTY_UNITS: dict[str, dict[str, float]] = {
    PA_S_PROPERTY: PA_S_UNIT_TO_PA_S,
    KINEMATIC_PROPERTY: KINEMATIC_UNIT_TO_M2_S,
}
PROPERTY_SI_UNIT: dict[str, str] = {
    PA_S_PROPERTY: "Pa*s",
    KINEMATIC_PROPERTY: "m2/s",
}
PROPERTY_SI_RANGE: dict[str, tuple[float, float]] = {
    PA_S_PROPERTY: (1e-6, 1e3),
    KINEMATIC_PROPERTY: (1e-10, 1e-3),
}

MIN_T_K = 100.0
MAX_T_K = 1000.0
EXACT_T_TOLERANCE_K = 1e-3
NEAREST_T_TOLERANCE_K = 1.0
MIN_RHO_KG_M3 = 1.0
MAX_RHO_KG_M3 = 5000.0
CP_PER_PA_S = 1000.0

XML_WORKERS = 8
XML_POLITENESS_SECONDS = 0.05
XML_RETRIES = 2

GROUP_SPLITS = 5
LEAK_REFERENCE_SEED = 20260926

DEFAULT_PREREG = REPOSITORY_ROOT / "probes" / "build_viscosity_v02_prereg.json"
DEFAULT_SUMMARY = REPOSITORY_ROOT / "probes" / "viscosity_v02_summary.json"
DEFAULT_REPORT = REPOSITORY_ROOT / "reports" / "viscosity_v02.md"
DEFAULT_CATALOG_CACHE = REPOSITORY_ROOT / "data" / "external" / "thermoml_api"
DEFAULT_XML_CACHE = REPOSITORY_ROOT / "data" / "raw" / "thermoml_viscosity_pa_s"
DEFAULT_TABLE = REPOSITORY_ROOT / "data" / "viscosity_v02.csv"
DEFAULT_RAW = REPOSITORY_ROOT / "data" / "processed" / "viscosity_v02_raw.csv"
DEFAULT_DENSITY = REPOSITORY_ROOT / "data" / "density_v01.csv"
DEFAULT_LOCAL_OBS = REPOSITORY_ROOT / "data" / "processed" / "viscosity_observations_thermoml.csv"
DEFAULT_LOCAL_COVERAGE = REPOSITORY_ROOT / "probes" / "thermoml_viscosity_coverage_summary.json"

# 这两个 key 天然随运行变化（时间戳、本次请求记账与缓存命中），比对时剔除。
UNSTABLE_SUMMARY_KEYS: tuple[str, ...] = ("generated_at_utc", "run_provenance")

TABLE_COLUMNS: tuple[str, ...] = (
    "record_id",
    "inchikey",
    "smiles",
    "name",
    "T_K",
    "viscosity_Pa_s",
    "viscosity_cP",
    "value_origin",
    "property_name",
    "property_unit_raw",
    "property_value_raw",
    "unit_conversion_factor",
    "uncertainty",
    "uncertainty_kind",
    "phase",
    "method_name",
    "pressure_kPa",
    "density_kg_m3_used",
    "density_T_K_used",
    "density_source_doi",
    "density_thermoml_file",
    "density_delta_t_k",
    "density_pairing_tolerance_k",
    "source_priority",
    "duplicate_of_local",
    "source_doi",
    "thermoml_file",
    "source_row_index",
)

RAW_COLUMNS: tuple[str, ...] = (
    "record_id",
    "inchikey",
    "inchi",
    "smiles",
    "name",
    "T_K",
    "property_name",
    "property_value_raw",
    "property_unit_raw",
    "property_value_si",
    "si_unit",
    "unit_conversion_factor",
    "quality_flag",
    "role",
    "component_count",
    "uncertainty",
    "uncertainty_kind",
    "phase",
    "method_name",
    "pressure_kPa",
    "source_doi",
    "thermoml_file",
    "source_row_index",
)

_BUDGET_LOCK = threading.Lock()


# --------------------------------------------------------------------------------------
# HTTP + 原始响应缓存（目录层）
# --------------------------------------------------------------------------------------

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
# 观测行抽取：单位归一与质量分档
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
# CSV 文本
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

def read_text_raw(path: Path) -> str:
    with path.open(encoding="utf-8", newline="") as handle:
        return handle.read()

def record_structured_property_names(record: Mapping[str, Any]) -> set[str]:
    """一条目录记录里出现过的结构化 ePropName（含 data_summary 的属性键）。"""

    names: set[str] = set()
    content = record.get("content") or {}
    if not isinstance(content, Mapping):
        return names
    for block in content.get("PureOrMixtureData", []) or []:
        if isinstance(block, Mapping):
            names |= block_property_names(block)
    summary = content.get("data_summary") or {}
    if isinstance(summary, Mapping):
        for section in summary.values():
            if not isinstance(section, Mapping):
                continue
            for key in section:
                if isinstance(key, str) and key.strip():
                    names.add(key.strip())
    return names


def record_has_pure_property(record: Mapping[str, Any], property_name: str) -> bool:
    """目录层判定：该记录是否含纯组分（单 Component）的该属性数据点。"""

    content = record.get("content") or {}
    if not isinstance(content, Mapping):
        return False
    for block in content.get("PureOrMixtureData", []) or []:
        if not isinstance(block, Mapping):
            continue
        if len(block.get("Component") or []) != 1:
            continue
        if property_name in block_property_names(block):
            return True
    summary = content.get("data_summary") or {}
    if isinstance(summary, Mapping):
        pure = summary.get("pure") or {}
        if isinstance(pure, Mapping):
            for section in pure.values():
                if not isinstance(section, Mapping):
                    continue
                entry = section.get(property_name) or {}
                if isinstance(entry, Mapping):
                    points = entry.get("data_points")
                    if isinstance(points, (int, float)) and points > 0:
                        return True
    return False


def catalog_page_descriptor(payload: Mapping[str, Any], property_name: str) -> dict[str, Any]:
    records = payload.get("results", []) or []
    dois: list[str] = []
    without_doi = 0
    keys: set[str] = set()
    property_names: dict[str, int] = {}
    structured_hit_dois: list[str] = []
    pure_property_dois: list[str] = []
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
        names = record_structured_property_names(record)
        for name in names:
            property_names[name] = property_names.get(name, 0) + 1
        if property_name in names:
            structured_hit_dois.append(doi)
        if record_has_pure_property(record, property_name):
            pure_property_dois.append(doi)
    return {
        "records": len(records),
        "dois": dois,
        "without_doi": without_doi,
        "keys": keys,
        "property_names": property_names,
        "structured_hit_dois": structured_hit_dois,
        "pure_property_dois": pure_property_dois,
        "size": int(payload.get("size", len(records)) or 0),
    }


def collect_one_slice(
    *,
    query: str,
    slug: str,
    property_name: str,
    cache_dir: Path,
    online: bool,
    refresh: bool,
    http_get: HttpGet,
    budget: RequestBudget,
    ledger: list[dict[str, Any]],
) -> dict[str, Any]:
    """抓全一个切片：先取首页拿 size，再从 pageNum=0 顺序抓满 ceil(size / pageSize) 页。"""

    first = fetch_page(
        query,
        PAGE_SIZE,
        FIRST_PAGE_NUM,
        slug=slug,
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
    structured_hit_dois: list[str] = []
    pure_property_dois: list[str] = []
    property_names: dict[str, int] = {}
    without_doi = 0
    records_collected = 0
    failed_pages: list[dict[str, Any]] = []
    sources: set[str] = {str(first["source"])}

    def absorb(payload: Mapping[str, Any]) -> None:
        nonlocal records_collected, without_doi
        descriptor = catalog_page_descriptor(payload, property_name)
        records_collected += int(descriptor["records"])
        without_doi += int(descriptor["without_doi"])
        dois.extend(descriptor["dois"])
        compound_keys.update(descriptor["keys"])
        structured_hit_dois.extend(descriptor["structured_hit_dois"])
        pure_property_dois.extend(descriptor["pure_property_dois"])
        for name, count in descriptor["property_names"].items():
            property_names[name] = property_names.get(name, 0) + int(count)

    absorb(first_payload)
    del first_payload
    for page_num in range(FIRST_PAGE_NUM + 1, FIRST_PAGE_NUM + pages):
        try:
            extra = fetch_page(
                query,
                PAGE_SIZE,
                page_num,
                slug=slug,
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

    return {
        "id": slug,
        "query": query,
        "property_name": property_name,
        "page_size": PAGE_SIZE,
        "size_records": size,
        "pages_fetched": pages,
        "records_collected": records_collected,
        "records_without_doi": without_doi,
        "unique_dois": len(set(dois)),
        "dois": sorted(set(dois)),
        "records_with_structured_property_name": len(set(structured_hit_dois)),
        "structured_property_hit_dois": sorted(set(structured_hit_dois)),
        "records_with_pure_property": len(set(pure_property_dois)),
        "pure_property_dois": sorted(set(pure_property_dois)),
        "structured_property_name_counts": dict(
            sorted(property_names.items(), key=lambda item: (-item[1], item[0]))
        ),
        "compound_keys": sorted(compound_keys),
        "failed_pages": failed_pages,
        "sources": sorted(sources),
    }


def collect_catalog(
    *,
    cache_dir: Path,
    online: bool,
    refresh: bool,
    http_get: HttpGet,
    budget: RequestBudget,
    ledger: list[dict[str, Any]],
) -> dict[str, Any]:
    """抓全目录层：* 总记录数 + Pa*s 切片 + kinematic 切片。"""

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

    pa_s = collect_one_slice(
        query=PA_S_QUERY,
        slug=PA_S_SLUG,
        property_name=PA_S_PROPERTY,
        cache_dir=cache_dir,
        online=online,
        refresh=refresh,
        http_get=http_get,
        budget=budget,
        ledger=ledger,
    )
    kinematic = collect_one_slice(
        query=KINEMATIC_QUERY,
        slug=KINEMATIC_SLUG,
        property_name=KINEMATIC_PROPERTY,
        cache_dir=cache_dir,
        online=online,
        refresh=refresh,
        http_get=http_get,
        budget=budget,
        ledger=ledger,
    )
    sources = sorted(set(pa_s.pop("sources")) | set(kinematic.pop("sources")))
    union = sorted(set(pa_s["dois"]) | set(kinematic["dois"]))
    return {
        "total_records": {"query": TOTAL_RECORDS_QUERY, "size_records": total_size},
        "slices": {"viscosity_pa_s": pa_s, "kinematic_viscosity": kinematic},
        "doi_union": union,
        "doi_intersection": sorted(set(pa_s["dois"]) & set(kinematic["dois"])),
        "sources": sources,
    }


def project_row(row: Mapping[str, str], *, inchi_cache: dict[str, str]) -> dict[str, str]:
    """把解析器的一行黏度观测投影成带质量分档的原始层行。"""

    property_name = (row.get("property_name") or "").strip()
    unit = (row.get("property_unit") or "").strip()
    raw_value = (row.get("property_value") or "").strip()
    value = to_float(raw_value)
    t_k = to_float(row.get("temperature_value"))
    table = ACCEPTED_PROPERTY_UNITS.get(property_name, {})
    factor = table.get(unit)
    si_value: float | None = None
    if value is not None and factor is not None:
        si_value = value * factor
    low, high = PROPERTY_SI_RANGE.get(property_name, (None, None))

    if factor is None:
        quality = "unit_rejected"
    elif t_k is None or not (MIN_T_K < t_k < MAX_T_K):
        quality = "temperature_rejected"
    elif si_value is None or not (low is not None and high is not None and low < si_value < high):
        quality = "value_rejected"
    else:
        quality = "accepted"

    component_count = (row.get("component_count") or "").strip()
    role = "pure" if component_count == "1" else "multi_component_deferred"
    inchi = (row.get("primary_compound_inchi") or "").strip()
    return {
        "inchikey": (row.get("primary_compound_inchi_key") or "").strip(),
        "inchi": inchi,
        "smiles": inchi_to_smiles(inchi, inchi_cache),
        "name": (row.get("primary_compound_name") or "").strip(),
        "T_K": "" if t_k is None else fmt_number(t_k),
        "property_name": property_name,
        "property_value_raw": raw_value,
        "property_unit_raw": unit,
        "property_value_si": "" if si_value is None else fmt_number(si_value),
        "si_unit": PROPERTY_SI_UNIT.get(property_name, ""),
        "unit_conversion_factor": "" if factor is None else fmt_number(factor),
        "quality_flag": quality,
        "role": role,
        "component_count": component_count,
        "uncertainty": (row.get("property_uncertainty") or "").strip(),
        "uncertainty_kind": (row.get("property_uncertainty_kind") or "").strip(),
        "phase": (row.get("phase") or "").strip(),
        "method_name": (row.get("method_name") or "").strip(),
        "pressure_kPa": pressure_kpa(row.get("constraints_json") or ""),
        "source_doi": (row.get("doi") or "").strip(),
        "thermoml_file": (row.get("source_file") or "").strip(),
        "source_row_index": (row.get("source_row_index") or "").strip(),
    }


def extract_value_layer(xml_results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    inchi_cache: dict[str, str] = {}
    raw_rows: list[dict[str, str]] = []
    total_named = 0
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
            if (row.get("property_name") or "").strip() not in ACCEPTED_PROPERTY_UNITS:
                continue
            total_named += 1
            raw_rows.append(project_row(row, inchi_cache=inchi_cache))
    raw_rows.sort(
        key=lambda item: (item["thermoml_file"], int(item["source_row_index"] or "0"))
    )
    return {
        "source": "thermoml_xml",
        "raw_rows": raw_rows,
        "total_named_viscosity_rows": total_named,
        "parse_failures": parse_failures,
        "smiles_unresolved": sum(
            1 for row in raw_rows if row["quality_flag"] == "accepted" and not row["smiles"]
        ),
    }


def ledger_from_raw(raw_rows: Sequence[Mapping[str, str]]) -> dict[str, int]:
    ledger = {
        "accepted_pure_rows": 0,
        "multi_component_deferred_rows": 0,
        "unit_rejected_rows": 0,
        "temperature_rejected_rows": 0,
        "value_rejected_rows": 0,
    }
    for row in raw_rows:
        flag = row["quality_flag"]
        if flag == "accepted":
            if row["role"] == "pure":
                ledger["accepted_pure_rows"] += 1
            else:
                ledger["multi_component_deferred_rows"] += 1
        else:
            ledger[flag + "_rows"] = ledger.get(flag + "_rows", 0) + 1
    return ledger


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


def read_local_observations(path: Path) -> dict[str, Any]:
    rows = read_csv_rows(path)
    return {
        "all_rows": rows,
        "pa_s_rows": [r for r in rows if (r.get("property_name") or "").strip() == PA_S_PROPERTY],
        "kinematic_rows": [
            r for r in rows if (r.get("property_name") or "").strip() == KINEMATIC_PROPERTY
        ],
    }


def observation_key(row: Mapping[str, str], *, with_row_index: bool) -> tuple[str, ...]:
    temperature = to_float(row.get("T_K"))
    parts = [
        (row.get("source_doi") or "").strip(),
        (row.get("inchikey") or "").strip(),
        "" if temperature is None else fmt_number(temperature),
    ]
    if with_row_index:
        parts.append((row.get("source_row_index") or "").strip())
    return tuple(parts)


def reconcile_local_pa_s(
    raw_rows: Sequence[Mapping[str, str]], local_rows: Sequence[Mapping[str, str]]
) -> dict[str, Any]:
    """逐行对账：本地 Pa*s 行 vs 在线收割的 Pa*s 行（同 DOI 同物质同温度 + 行号）。不合并、不平均。"""

    online_index: dict[tuple[str, ...], list[Mapping[str, str]]] = {}
    for row in raw_rows:
        if row["property_name"] != PA_S_PROPERTY:
            continue
        online_index.setdefault(observation_key(row, with_row_index=True), []).append(row)
    online_keys3 = {
        observation_key(row, with_row_index=False)
        for row in raw_rows
        if row["property_name"] == PA_S_PROPERTY
    }

    matched_rows = 0
    matched_keys: set[tuple[str, ...]] = set()
    matched_keys3: set[tuple[str, ...]] = set()
    unmatched: list[dict[str, str]] = []
    for row in local_rows:
        key = observation_key(row, with_row_index=True)
        key3 = observation_key(row, with_row_index=False)
        if key in online_index:
            matched_rows += 1
            matched_keys.add(key)
            matched_keys3.add(key3)
        else:
            unmatched.append(
                {
                    "source_doi": (row.get("source_doi") or "").strip(),
                    "inchikey": (row.get("inchikey") or "").strip(),
                    "T_K": (row.get("T_K") or "").strip(),
                    "source_row_index": (row.get("source_row_index") or "").strip(),
                    "key3_also_present": key3 in online_keys3,
                }
            )
    online_only = sorted(key for key in online_index if key not in matched_keys)
    return {
        "property_name": PA_S_PROPERTY,
        "local_rows": len(local_rows),
        "matched_local_rows": matched_rows,
        "unmatched_local_rows": len(unmatched),
        "unmatched_local_examples": unmatched[:10],
        "online_pa_s_rows": sum(1 for row in raw_rows if row["property_name"] == PA_S_PROPERTY),
        "online_only_row_keys": len(online_only),
        "matched_row_keys": matched_keys,
        "matched_key3": matched_keys3,
        "local_key3": {observation_key(row, with_row_index=False) for row in local_rows},
        "online_key3": online_keys3,
    }


def pair_kinematic_rows(
    kinematic_rows: Sequence[Mapping[str, str]],
    density_rows: Sequence[Mapping[str, str]],
) -> dict[str, Any]:
    """把本地运动黏度行逐行配到密度行（exact 1e-3 K 与 nearest <= 1.0 K），并反解 eta = kappa * rho。"""

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
    converted_rows = 0
    pooled_rows = 0
    for row in kinematic_rows:
        key = (row.get("inchikey") or "").strip()
        temperature = to_float(row.get("T_K"))
        kappa = to_float(row.get("viscosity_kinematic_m2_s"))
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
                    or (
                        nearest_hit is not None
                        and abs(delta - best_delta) <= 1e-12
                        and candidate_temperature < nearest_hit[0]
                    )
                ):
                    best_delta = delta
                    nearest_hit = (candidate_temperature, candidate)
        is_pure = (row.get("n_components") or "").strip() == "1"
        eta: float | None = None
        rho: float | None = None
        if nearest_hit is not None:
            rho = to_float(nearest_hit[1].get("density_kg_m3"))
            if kappa is not None and rho is not None:
                eta = kappa * rho
        if exact_hit is not None:
            exact_rows += 1
        if nearest_hit is not None:
            nearest_rows += 1
        if eta is not None:
            converted_rows += 1
            if is_pure:
                pooled_rows += 1
        entry: dict[str, Any] = {
            "inchikey": key,
            "name": (row.get("name") or "").strip(),
            "T_K": "" if temperature is None else fmt_number(temperature),
            "viscosity_kinematic_m2_s": "" if kappa is None else fmt_number(kappa),
            "n_components": (row.get("n_components") or "").strip(),
            "is_pure": is_pure,
            "viscosity_source_doi": (row.get("source_doi") or "").strip(),
            "viscosity_thermoml_file": (row.get("thermoml_file") or "").strip(),
            "viscosity_source_row_index": (row.get("source_row_index") or "").strip(),
            "exact": exact_hit is not None,
            "nearest": nearest_hit is not None,
            "converted_pa_s": "" if eta is None else fmt_number(eta),
            "pooled_into_main_table": bool(eta is not None and is_pure),
        }
        if nearest_hit is not None:
            delta = abs(nearest_hit[0] - (temperature or 0.0))
            entry["delta_t_k"] = round(delta, 6)
            entry["density_T_K"] = fmt_number(nearest_hit[0])
            entry["density_kg_m3"] = (nearest_hit[1].get("density_kg_m3") or "").strip()
            entry["density_source_doi"] = (nearest_hit[1].get("source_doi") or "").strip()
            entry["density_thermoml_file"] = (
                nearest_hit[1].get("thermoml_file") or ""
            ).strip()
            entry["density_source_row_index"] = (
                nearest_hit[1].get("source_row_index") or ""
            ).strip()
        else:
            entry["delta_t_k"] = None
            entry["density_T_K"] = ""
            entry["density_kg_m3"] = ""
            entry["density_source_doi"] = ""
            entry["density_thermoml_file"] = ""
            entry["density_source_row_index"] = ""
        per_row.append(entry)

    by_key: dict[str, dict[str, int]] = {}
    for entry in per_row:
        bucket = by_key.setdefault(
            entry["inchikey"], {"rows": 0, "exact": 0, "nearest": 0, "pooled": 0}
        )
        bucket["rows"] += 1
        bucket["exact"] += int(entry["exact"])
        bucket["nearest"] += int(entry["nearest"])
        bucket["pooled"] += int(entry["pooled_into_main_table"])

    return {
        "local_rows": len(per_row),
        "local_keys": len(by_key),
        "exact_rows": exact_rows,
        "nearest_rows": nearest_rows,
        "converted_rows": converted_rows,
        "pooled_rows": pooled_rows,
        "deferred_multi_component_rows": converted_rows - pooled_rows,
        "exact_tolerance_k": EXACT_T_TOLERANCE_K,
        "nearest_tolerance_k": NEAREST_T_TOLERANCE_K,
        "by_key": dict(sorted(by_key.items())),
        "per_row": per_row,
    }


def run_group_audit(rows: Sequence[Mapping[str, str]]) -> dict[str, Any]:
    """联表重建时跑一次真 GroupKFold by InChIKey：组泄漏即停工，不是告警。

    random_row 只作泄漏参照，永远不进任何判决。
    """

    from sklearn.model_selection import GroupKFold, KFold

    groups = [str(row["inchikey"]) for row in rows if row.get("inchikey")]
    usable = [row for row in rows if row.get("inchikey")]
    if len(usable) < GROUP_SPLITS or len(set(groups)) < GROUP_SPLITS:
        return {
            "splitter": "GroupKFold by InChIKey",
            "group_key": "inchikey",
            "n_splits": GROUP_SPLITS,
            "subset": "viscosity_v02 主表行（重建的联表）",
            "subset_rows": len(usable),
            "subset_groups": len(set(groups)),
            "assertion": "group_overlap == 0 between train and test groups",
            "assertion_passed": False,
            "max_group_overlap": None,
            "folds": [],
            "random_row": {
                "role": "leak reference only; it never enters a verdict",
                "splitter": "KFold(shuffle=True) on rows",
                "seed": LEAK_REFERENCE_SEED,
                "test_rows": 0,
                "test_rows_whose_group_also_sits_in_train": 0,
                "leaked_fraction": None,
            },
            "error": "not enough rows or groups to run the split",
        }
    folds: list[dict[str, Any]] = []
    max_overlap = 0
    for fold, (train_index, test_index) in enumerate(
        GroupKFold(n_splits=GROUP_SPLITS).split(usable, groups=groups)
    ):
        train_groups = {groups[index] for index in train_index}
        test_groups = {groups[index] for index in test_index}
        overlap = len(train_groups & test_groups)
        max_overlap = max(max_overlap, overlap)
        folds.append(
            {
                "fold": fold,
                "train_rows": len(train_index),
                "test_rows": len(test_index),
                "train_groups": len(train_groups),
                "test_groups": len(test_groups),
                "group_overlap": overlap,
            }
        )
    if max_overlap != 0:
        raise RuntimeError(
            f"GroupKFold by InChIKey leaked {max_overlap} groups across train/test: "
            "this is a stop, not a warning"
        )
    leak_rows = 0
    test_rows = 0
    for train_index, test_index in KFold(
        n_splits=GROUP_SPLITS, shuffle=True, random_state=LEAK_REFERENCE_SEED
    ).split(usable):
        train_groups = {groups[index] for index in train_index}
        test_rows += len(test_index)
        leak_rows += sum(1 for index in test_index if groups[index] in train_groups)
    return {
        "splitter": "GroupKFold by InChIKey",
        "group_key": "inchikey",
        "n_splits": GROUP_SPLITS,
        "subset": "viscosity_v02 主表行（重建的联表）",
        "subset_rows": len(usable),
        "subset_groups": len(set(groups)),
        "assertion": "group_overlap == 0 between train and test groups",
        "assertion_passed": max_overlap == 0,
        "max_group_overlap": max_overlap,
        "folds": folds,
        "random_row": {
            "role": "leak reference only; it never enters a verdict",
            "splitter": "KFold(shuffle=True) on rows",
            "seed": LEAK_REFERENCE_SEED,
            "test_rows": test_rows,
            "test_rows_whose_group_also_sits_in_train": leak_rows,
            "leaked_fraction": round(leak_rows / test_rows, 6) if test_rows else None,
        },
    }


def main_rows_from_raw(
    raw_rows: Sequence[Mapping[str, str]], *, matched_row_keys: set[tuple[str, ...]]
) -> list[dict[str, str]]:
    """主表行：在线收割里「纯组分 + 质量分档 accepted」的 Pa*s 观测行（运动黏度走解冻路径）。"""

    rows: list[dict[str, str]] = []
    for row in raw_rows:
        if row["quality_flag"] != "accepted" or row["role"] != "pure":
            continue
        if row["property_name"] != PA_S_PROPERTY:
            continue
        duplicate = observation_key(row, with_row_index=True) in matched_row_keys
        rows.append(
            {
                "record_id": "",
                "inchikey": row["inchikey"],
                "smiles": row["smiles"],
                "name": row["name"],
                "T_K": row["T_K"],
                "viscosity_Pa_s": row["property_value_si"],
                "viscosity_cP": _times(row["property_value_si"], CP_PER_PA_S),
                "value_origin": "pa_s_measured",
                "property_name": row["property_name"],
                "property_unit_raw": row["property_unit_raw"],
                "property_value_raw": row["property_value_raw"],
                "unit_conversion_factor": row["unit_conversion_factor"],
                "uncertainty": row["uncertainty"],
                "uncertainty_kind": row["uncertainty_kind"],
                "phase": row["phase"],
                "method_name": row["method_name"],
                "pressure_kPa": row["pressure_kPa"],
                "density_kg_m3_used": "",
                "density_T_K_used": "",
                "density_source_doi": "",
                "density_thermoml_file": "",
                "density_delta_t_k": "",
                "density_pairing_tolerance_k": "",
                "source_priority": "online_duplicate_of_local" if duplicate else "online_new",
                "duplicate_of_local": "true" if duplicate else "false",
                "source_doi": row["source_doi"],
                "thermoml_file": row["thermoml_file"],
                "source_row_index": row["source_row_index"],
            }
        )
    return rows


def _times(text: str, factor: float) -> str:
    value = to_float(text)
    if value is None:
        return ""
    return fmt_number(value * factor)


def main_rows_from_unfreeze(pairing: Mapping[str, Any]) -> list[dict[str, str]]:
    """主表行：本地纯组分运动黏度行用 rho(T) 反解 eta = kappa * rho（逐行带换算 provenance）。"""

    rows: list[dict[str, str]] = []
    for entry in pairing["per_row"]:
        if not entry["pooled_into_main_table"]:
            continue
        eta = to_float(entry["converted_pa_s"])
        if eta is None:
            continue
        rows.append(
            {
                "record_id": "",
                "inchikey": entry["inchikey"],
                "smiles": "",
                "name": entry["name"],
                "T_K": entry["T_K"],
                "viscosity_Pa_s": fmt_number(eta),
                "viscosity_cP": fmt_number(eta * CP_PER_PA_S),
                "value_origin": "kinematic_converted",
                "property_name": KINEMATIC_PROPERTY,
                "property_unit_raw": "m2/s x kg/m3",
                "property_value_raw": entry["viscosity_kinematic_m2_s"],
                "unit_conversion_factor": entry["density_kg_m3"],
                "uncertainty": "",
                "uncertainty_kind": "",
                "phase": "Liquid",
                "method_name": "",
                "pressure_kPa": "",
                "density_kg_m3_used": entry["density_kg_m3"],
                "density_T_K_used": entry["density_T_K"],
                "density_source_doi": entry["density_source_doi"],
                "density_thermoml_file": entry["density_thermoml_file"],
                "density_delta_t_k": "" if entry["delta_t_k"] is None else fmt_number(
                    float(entry["delta_t_k"])
                ),
                "density_pairing_tolerance_k": fmt_number(NEAREST_T_TOLERANCE_K),
                "source_priority": "local_kinematic_unfrozen",
                "duplicate_of_local": "",
                "source_doi": entry["viscosity_source_doi"],
                "thermoml_file": entry["viscosity_thermoml_file"],
                "source_row_index": entry["viscosity_source_row_index"],
            }
        )
    return rows


def finalize_table_rows(rows: Sequence[Mapping[str, str]]) -> list[dict[str, str]]:
    ordered = sorted(
        rows,
        key=lambda item: (
            item["source_doi"],
            item["thermoml_file"],
            int(item["source_row_index"] or "0"),
            item["value_origin"],
        ),
    )
    finalized: list[dict[str, str]] = []
    for index, row in enumerate(ordered):
        clone = {column: row.get(column, "") for column in TABLE_COLUMNS}
        clone["record_id"] = str(index)
        finalized.append(clone)
    return finalized


# --------------------------------------------------------------------------------------
# 判据
# --------------------------------------------------------------------------------------


def evaluate_criterion_a(
    dataset: Mapping[str, Any], prereg: Mapping[str, Any]
) -> dict[str, Any]:
    expected = prereg["frozen_expectations"]
    slices = dataset["slices"]
    total_records = int(dataset["total_records"]["size_records"])
    violations: list[str] = []
    if total_records != int(expected["total_records_size"]):
        violations.append(
            f"* 的在线 size 记录数 {total_records} 与预注册 {expected['total_records_size']} 不符"
        )

    pagination: dict[str, Any] = {}
    expected_pages = {
        PA_S_SLUG: int(expected["pa_s_slice_pages"]),
        KINEMATIC_SLUG: int(expected["kinematic_slice_pages"]),
    }
    expected_sizes = {
        PA_S_SLUG: int(expected["pa_s_slice_size"]),
        KINEMATIC_SLUG: int(expected["kinematic_slice_size"]),
    }
    for slug, slice_dataset in slices.items():
        size_records = int(slice_dataset["size_records"])
        records_collected = int(slice_dataset["records_collected"])
        pages_fetched = int(slice_dataset["pages_fetched"])
        unique_dois = int(slice_dataset["unique_dois"])
        failed_pages = list(slice_dataset.get("failed_pages", []))
        if size_records != expected_sizes[slug]:
            violations.append(
                f"{slug} 切片的在线 size 记录数 {size_records} 与预注册 {expected_sizes[slug]} 不符"
            )
        if pages_fetched != expected_pages[slug]:
            violations.append(
                f"{slug} 抓取页数 {pages_fetched} 与预注册 {expected_pages[slug]} 不符"
            )
        if records_collected != size_records:
            violations.append(
                f"{slug} 分页不全：抓到 {records_collected} 条记录 vs size 记录数 {size_records}"
            )
        if unique_dois != records_collected:
            violations.append(
                f"{slug} DOI 有重复：唯一 DOI {unique_dois} vs 抓到 {records_collected} 条记录"
            )
        if failed_pages:
            violations.append(f"{slug} 有失败页：{failed_pages}")
        pagination[slug] = {
            "page_size": int(slice_dataset["page_size"]),
            "page_num_base": FIRST_PAGE_NUM,
            "pages_fetched": pages_fetched,
            "expected_pages": expected_pages[slug],
            "size_records": size_records,
            "records_collected": records_collected,
            "unique_dois": unique_dois,
            "pagination_complete": records_collected == size_records,
            "dois_unique": unique_dois == records_collected,
            "failed_pages": failed_pages,
        }
    if FIRST_PAGE_NUM != 0:
        violations.append("分页不是从 pageNum=0 起")

    return {
        "id": "A",
        "expected_sizes": {
            "*": int(expected["total_records_size"]),
            PA_S_QUERY: int(expected["pa_s_slice_size"]),
            KINEMATIC_QUERY: int(expected["kinematic_slice_size"]),
        },
        "measured_sizes": {
            "*": total_records,
            PA_S_QUERY: int(slices[PA_S_SLUG]["size_records"]),
            KINEMATIC_QUERY: int(slices[KINEMATIC_SLUG]["size_records"]),
        },
        "pagination": pagination,
        "doi_union_records": len(dataset["doi_union"]),
        "doi_intersection_records": len(dataset["doi_intersection"]),
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
    local_dois: set[str],
    local_source: Mapping[str, Any],
    prereg: Mapping[str, Any],
) -> dict[str, Any]:
    online = set(dataset["doi_union"])
    missing = sorted(local_dois - online)
    violations: list[str] = []
    if missing:
        violations.append(f"本地含黏度 DOI 有 {len(missing)} 个不在在线清单里：{missing[:5]}")
    return {
        "id": "B",
        "local_source": dict(local_source),
        "local_doi_count": len(local_dois),
        "online_union_count": len(online),
        "hit_count": len(local_dois & online),
        "missing_dois": missing,
        "per_doi": [
            {"doi": doi, "in_online_union": doi in online} for doi in sorted(local_dois)
        ],
        "violations": violations,
        "n_violations": len(violations),
        "allowed_violations": int(
            prereg["pre_registered_criteria"]["B_local_subset_of_online"]["allowed_violations"]
        ),
        "passed": not violations,
    }


def evaluate_criterion_c(
    value_layer: Mapping[str, Any],
    table_rows: Sequence[Mapping[str, str]],
    prereg: Mapping[str, Any],
) -> dict[str, Any]:
    ledger = dict(value_layer["ledger"])
    total_named = int(value_layer["total_named_viscosity_rows"])
    ledger_total = sum(int(value) for value in ledger.values())
    violations: list[str] = []
    if ledger_total != total_named:
        violations.append(
            f"分档账本不平：账本合计 {ledger_total} vs 命中属性名总观测 {total_named}"
        )
    if not PA_S_UNIT_TO_PA_S or not KINEMATIC_UNIT_TO_M2_S:
        violations.append("单位换算表有空表：必须显式列全")
    measured_rows = sum(1 for row in table_rows if row["value_origin"] == "pa_s_measured")
    pa_s_accepted = int(value_layer.get("accepted_pure_pa_s_rows", 0))
    if measured_rows != pa_s_accepted:
        violations.append(
            f"主表 pa_s_measured 行数 {measured_rows} 与账本 accepted 纯组分 Pa*s 行 {pa_s_accepted} 不符"
        )
    return {
        "id": "C",
        "tiers": [
            "tier1 单位换算表（显式列全，不在表里即 unit_rejected）",
            "tier2 温度区间 (100, 1000) K，超出即 temperature_rejected",
            "tier3 数值区间 Pa*s (1e-6, 1e3) / m2/s (1e-10, 1e-3)，超出即 value_rejected",
        ],
        "unit_table": {
            PA_S_PROPERTY: PA_S_UNIT_TO_PA_S,
            KINEMATIC_PROPERTY: KINEMATIC_UNIT_TO_M2_S,
        },
        "ledger": ledger,
        "total_named_viscosity_rows": total_named,
        "unrecognized_units": value_layer.get("unrecognized_units", []),
        "accepted_pure_pa_s_rows": int(value_layer.get("accepted_pure_pa_s_rows", 0)),
        "accepted_pure_kinematic_rows": int(
            value_layer.get("accepted_pure_kinematic_rows", 0)
        ),
        "violations": violations,
        "n_violations": len(violations),
        "allowed_violations": int(
            prereg["pre_registered_criteria"]["C_unit_honesty"]["allowed_violations"]
        ),
        "passed": not violations,
    }


def evaluate_criterion_d(
    dataset: Mapping[str, Any],
    value_layer: Mapping[str, Any],
    table_rows: Sequence[Mapping[str, str]],
    reconciler: Mapping[str, Any],
    prereg: Mapping[str, Any],
) -> dict[str, Any]:
    machine = prereg["pre_registered_criteria"]["D_basis_honesty"]["machine_readable"]
    slices = dataset["slices"]
    violations: list[str] = []
    required = {
        "size_unit": "record",
        "online_row_count": "unknown",
        "value_basis": "thermoml_xml_observation_row",
        "must_report_dual_basis": True,
        "row_comparison_allowed": False,
    }
    for key, value in required.items():
        if machine.get(key) != value:
            violations.append(f"预注册 D 的机读字段 {key} 不是 {value}")

    raw_rows = value_layer["raw_rows"]
    dual = {
        "online_pa_s_slice_records": int(slices[PA_S_SLUG]["size_records"]),
        "online_kinematic_slice_records": int(slices[KINEMATIC_SLUG]["size_records"]),
        "online_union_records": len(dataset["doi_union"]),
        "raw_named_rows": int(value_layer["total_named_viscosity_rows"]),
        "raw_named_inchikeys": len(
            {row["inchikey"] for row in raw_rows if row["inchikey"]}
        ),
        "viscosity_v02_rows": len(table_rows),
        "viscosity_v02_inchikeys": len(
            {row["inchikey"] for row in table_rows if row["inchikey"]}
        ),
        "pa_s_measured_rows": sum(
            1 for row in table_rows if row["value_origin"] == "pa_s_measured"
        ),
        "kinematic_converted_rows": sum(
            1 for row in table_rows if row["value_origin"] == "kinematic_converted"
        ),
        "multi_component_deferred_rows": int(
            value_layer["ledger"].get("multi_component_deferred_rows", 0)
        ),
        "local_pa_s_rows_reconciled": int(reconciler["local_rows"]),
        "local_pa_s_rows_matched": int(reconciler["matched_local_rows"]),
    }
    return {
        "id": "D",
        "size_unit": "record",
        "size_unit_statement": "在线目录层的 size 是检索命中的 ThermoML 记录（文档）数，不是数据行数；"
        "它不能与本表（或任何 CSV）的观测行数相减或相除。",
        "online_row_count": "unknown",
        "online_row_count_reason": "JSON API 只暴露记录级元数据与 data_summary 计数，不含 NumValues 数值行"
        "（跑前侦察实测：整页记录里 nValue/PropertyValue 均出现 0 次），故在线行数只能记 unknown，不估。",
        "value_basis": "thermoml_xml_observation_row",
        "value_basis_statement": "本表的每一行都来自同一 DOI 的 ThermoML XML 的一个 NumValues 行"
        "（运动黏度换算行另标 value_origin=kinematic_converted），与在线记录数是两套口径，禁止相除当覆盖率。",
        "dual_basis_counts": dual,
        "dual_basis_statement": "记录数 != 观测行数 != InChIKey 数，三者分开报，禁止互相相除。",
        "row_comparison_allowed": False,
        "violations": violations,
        "n_violations": len(violations),
        "allowed_violations": int(
            prereg["pre_registered_criteria"]["D_basis_honesty"]["allowed_violations"]
        ),
        "passed": not violations,
    }


def accepted_pure_counts(raw_rows: Sequence[Mapping[str, str]]) -> dict[str, int]:
    counts = {"pa_s": 0, "kinematic": 0}
    for row in raw_rows:
        if row["quality_flag"] != "accepted" or row["role"] != "pure":
            continue
        if row["property_name"] == PA_S_PROPERTY:
            counts["pa_s"] += 1
        elif row["property_name"] == KINEMATIC_PROPERTY:
            counts["kinematic"] += 1
    return counts


def unrecognized_units(raw_rows: Sequence[Mapping[str, str]]) -> list[dict[str, Any]]:
    counter: dict[tuple[str, str], int] = {}
    for row in raw_rows:
        if row["quality_flag"] != "unit_rejected":
            continue
        key = (row["property_name"], row["property_unit_raw"])
        counter[key] = counter.get(key, 0) + 1
    return [
        {"property_name": name, "property_unit_raw": unit, "count": count}
        for (name, unit), count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    ]


def load_local_doi_source(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    entries = payload.get("files_with_viscosity") or []
    dois = sorted(
        {
            (entry.get("source_doi") or "").strip()
            for entry in entries
            if (entry.get("source_doi") or "").strip()
        }
    )
    return {
        "path": display_path(path),
        "sha256": sha256_file(path),
        "viscosity_files": int(payload.get("viscosity_files", len(entries))),
        "dois": dois,
    }


def slice_manifest(slice_dataset: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "query": slice_dataset["query"],
        "property_name": slice_dataset["property_name"],
        "page_size": int(slice_dataset["page_size"]),
        "size_records": int(slice_dataset["size_records"]),
        "pages_fetched": int(slice_dataset["pages_fetched"]),
        "records_collected": int(slice_dataset["records_collected"]),
        "unique_dois": int(slice_dataset["unique_dois"]),
        "records_with_structured_property_name": int(
            slice_dataset["records_with_structured_property_name"]
        ),
        "records_with_pure_property": int(slice_dataset["records_with_pure_property"]),
        "dois": list(slice_dataset["dois"]),
    }


def catalog_manifest(dataset: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "total_records": dict(dataset["total_records"]),
        "slices": {
            slug: slice_manifest(dataset["slices"][slug])
            for slug in (PA_S_SLUG, KINEMATIC_SLUG)
        },
        "doi_union": list(dataset["doi_union"]),
        "doi_intersection": list(dataset["doi_intersection"]),
    }


def build_summary(
    *,
    prereg: Mapping[str, Any],
    prereg_path: Path,
    prereg_sha256: str,
    dataset: Mapping[str, Any],
    value_layer: Mapping[str, Any],
    table_rows: Sequence[Mapping[str, str]],
    pairing: Mapping[str, Any],
    reconciler: Mapping[str, Any],
    local_doi_source: Mapping[str, Any],
    local_obs_counts: Mapping[str, Any],
    input_digests: Mapping[str, Any],
    outputs: Mapping[str, Any],
    run_provenance: Mapping[str, Any],
    generated_at: str,
) -> dict[str, Any]:
    criterion_a = evaluate_criterion_a(dataset, prereg)
    criterion_b = evaluate_criterion_b(dataset, set(local_doi_source["dois"]), local_doi_source, prereg)
    criterion_c = evaluate_criterion_c(value_layer, table_rows, prereg)
    criterion_d = evaluate_criterion_d(dataset, value_layer, table_rows, reconciler, prereg)
    group_audit = run_group_audit(table_rows)

    manifest = catalog_manifest(dataset)
    manifest_sha = sha256_text(canonical_json(manifest))
    unique_keys = sorted({row["inchikey"] for row in table_rows if row["inchikey"]})
    findings = [
        (
            "目录层：检索词 * 的在线 size 是 {} 条记录；\"Viscosity, Pa*s\" 切片的 size 是 {} 条记录（{} 页，"
            "pageNum=0 起）、\"Kinematic viscosity, m2/s\" 切片的 size 是 {} 条记录（{} 页），两个切片都抓全、"
            "DOI 唯一。两个切片 DOI 并集 {} 条记录，交集 {} 条记录。"
        ).format(
            dataset["total_records"]["size_records"],
            dataset["slices"][PA_S_SLUG]["size_records"],
            dataset["slices"][PA_S_SLUG]["pages_fetched"],
            dataset["slices"][KINEMATIC_SLUG]["size_records"],
            dataset["slices"][KINEMATIC_SLUG]["pages_fetched"],
            len(dataset["doi_union"]),
            len(dataset["doi_intersection"]),
        ),
        (
            "数值层：从两个切片 DOI 并集的 ThermoML XML 里抽出黏度观测 {} 条；其中纯组分接受 {} 条、"
            "多组分另册登记 {} 条；未识别单位 {} 条、超范围温度 {} 条、非法值 {} 条。"
        ).format(
            value_layer["total_named_viscosity_rows"],
            value_layer["ledger"].get("accepted_pure_rows", 0),
            value_layer["ledger"].get("multi_component_deferred_rows", 0),
            value_layer["ledger"].get("unit_rejected_rows", 0),
            value_layer["ledger"].get("temperature_rejected_rows", 0),
            value_layer["ledger"].get("value_rejected_rows", 0),
        ),
        (
            "主表 viscosity_v02：{} 行 = Pa*s 直测 {} 行 + 本地运动黏度用 rho(T) 反解 {} 行；"
            "唯一 InChIKey {} 个。"
        ).format(
            len(table_rows),
            criterion_d["dual_basis_counts"]["pa_s_measured_rows"],
            criterion_d["dual_basis_counts"]["kinematic_converted_rows"],
            len(unique_keys),
        ),
        (
            "本地对账：本地 Pa*s 观测 {} 行，与在线收割逐行（同 DOI 同物质同温度同行号）命中 {} 行；"
            "未命中 {} 行。重复行只标 source_priority，不合并、不平均。"
        ).format(
            reconciler["local_rows"],
            reconciler["matched_local_rows"],
            reconciler["unmatched_local_rows"],
        ),
        (
            "解冻指标：本地运动黏度 {} 行（{} 个化合物）；exact（|dT| <= {} K）配到密度 {} 行、"
            "nearest（|dT| <= {} K）配到 {} 行；反解出 eta 的 {} 行，其中纯组分入主表 {} 行、"
            "多组分另册 {} 行。"
        ).format(
            pairing["local_rows"],
            pairing["local_keys"],
            pairing["exact_tolerance_k"],
            pairing["exact_rows"],
            pairing["nearest_tolerance_k"],
            pairing["nearest_rows"],
            pairing["converted_rows"],
            pairing["pooled_rows"],
            pairing["deferred_multi_component_rows"],
        ),
        (
            "本地 ⊆ 在线：本地含黏度 DOI {} 个全部命中所抓在线并集（{} 条记录口径）。"
        ).format(criterion_b["local_doi_count"], criterion_b["online_union_count"]),
        (
            "联表重建 group_overlap 断言：GroupKFold by InChIKey（{} 折，{} 行 / {} 组）"
            "max_group_overlap = {}；random_row 只作泄漏参照（leaked_fraction = {}）。"
        ).format(
            group_audit["n_splits"],
            group_audit["subset_rows"],
            group_audit["subset_groups"],
            group_audit["max_group_overlap"],
            group_audit["random_row"]["leaked_fraction"],
        ),
    ]
    limitations = [
        (
            "在线目录层的 size 是记录数，不是数据行数；在线行数记 unknown（JSON API 不含数值行），"
            "本表不给出任何以在线记录数为分母的行口径覆盖率。"
        ),
        (
            "本表的行是 ThermoML XML 的 NumValues 观测行（运动黏度换算行另标 value_origin），"
            "与目录层记录数是两套口径；XML 数值层来自 " + XML_BASE + "/{doi}.xml，与目录层同源同 DOI，"
            "但不是同一份字节。"
        ),
        (
            "多组分记录未做溶质/溶剂角色拆分，一律另册登记（raw 层 role=multi_component_deferred，"
            "以及解冻账本 per_row 里 pooled_into_main_table=false 的行），不入主表。"
        ),
        (
            "运动黏度另册：在线 kinematic 切片的纯组分接受行共 {} 行（含本地 176 行作为子集），"
            "本臂按预注册范围只反解本地 176 行，其中纯组分 {} 行入主表；其余纯组分运动黏度行"
            "只入 raw 另册，未做换算。"
        ).format(
            value_layer["accepted_pure_kinematic_rows"], pairing["pooled_rows"]
        ),
        (
            "运动黏度换算只做「同 InChIKey（主组分）+ 同温度（exact）或最近邻且 |dT| <= 1.0 K」的配对，"
            "不插值、不外推；换算式 eta = kappa * rho，rho 取 data/density_v01.csv 的纯组分密度，"
            "逐行 provenance 见主表 density_* 列与 summary 的 criterion_c_unfreeze.per_row。"
        ),
        (
            "本地 Pa*s 行与在线收割行的对账口径是「同 DOI + 同 InChIKey + 同温度 + 同源行号」；"
            "重复行只标 source_priority，不做平均、不做去重。"
        ),
        "本臂只建表与计数：不拟合模型、不产 R2/MAE、不改任何既有文件。",
    ]
    return {
        "schema_version": 1,
        "task": "build_viscosity_v02",
        "generated_at_utc": generated_at,
        "prereg": {
            "path": display_path(prereg_path),
            "sha256": prereg_sha256,
            "locked_at_utc": prereg["locked_at_utc"],
            "status": prereg["status"],
        },
        "api": dict(prereg["api"]),
        "inputs": dict(input_digests),
        "local_observation_counts": dict(local_obs_counts),
        "dataset": dict(dataset, manifest_sha256=manifest_sha),
        "value_layer": {
            "source": value_layer["source"],
            "total_named_viscosity_rows": int(value_layer["total_named_viscosity_rows"]),
            "ledger": dict(value_layer["ledger"]),
            "unique_keys": int(value_layer["unique_keys"]),
            "accepted_pure_pa_s_rows": int(value_layer["accepted_pure_pa_s_rows"]),
            "accepted_pure_kinematic_rows": int(value_layer["accepted_pure_kinematic_rows"]),
            "unrecognized_units": list(value_layer["unrecognized_units"]),
            "temperature_distribution": list(value_layer["temperature_distribution"]),
            "parse_failures": list(value_layer.get("parse_failures", [])),
            "smiles_unresolved": int(value_layer.get("smiles_unresolved", 0)),
            "accepted_property_units": {
                PA_S_PROPERTY: dict(PA_S_UNIT_TO_PA_S),
                KINEMATIC_PROPERTY: dict(KINEMATIC_UNIT_TO_M2_S),
            },
            "xml_status": dict(value_layer.get("xml_status", {})),
        },
        "criterion_a_online_slice": criterion_a,
        "criterion_b_local_subset": criterion_b,
        "criterion_c_unit_honesty": criterion_c,
        "criterion_d_basis_honesty": criterion_d,
        "criterion_e_row_reconciliation": {
            "id": "E",
            "local_rows": int(reconciler["local_rows"]),
            "matched_local_rows": int(reconciler["matched_local_rows"]),
            "unmatched_local_rows": int(reconciler["unmatched_local_rows"]),
            "unmatched_local_examples": list(reconciler["unmatched_local_examples"]),
            "online_pa_s_rows": int(reconciler["online_pa_s_rows"]),
            "online_only_row_keys": int(reconciler["online_only_row_keys"]),
            "averaging_applied": False,
            "statement": "逐行对账只标 source_priority，不合并、不平均。",
        },
        "criterion_c_unfreeze": {
            "id": "C",
            "local_rows": int(pairing["local_rows"]),
            "local_keys": int(pairing["local_keys"]),
            "exact_rows": int(pairing["exact_rows"]),
            "nearest_rows": int(pairing["nearest_rows"]),
            "converted_rows": int(pairing["converted_rows"]),
            "pooled_rows": int(pairing["pooled_rows"]),
            "deferred_multi_component_rows": int(pairing["deferred_multi_component_rows"]),
            "exact_tolerance_k": float(pairing["exact_tolerance_k"]),
            "nearest_tolerance_k": float(pairing["nearest_tolerance_k"]),
            "by_key": dict(pairing["by_key"]),
            "per_row": [dict(entry) for entry in pairing["per_row"]],
            "violations": (
                [] if pairing["local_rows"] == int(prereg["frozen_expectations"]["local_kinematic_rows"])
                else [
                    "本地运动黏度逐行判定 {} 条 vs 预注册 {} 行".format(
                        pairing["local_rows"],
                        prereg["frozen_expectations"]["local_kinematic_rows"],
                    )
                ]
            ),
        },
        "group_overlap_audit": group_audit,
        "unique_inchikeys": unique_keys,
        "outputs": dict(outputs),
        "run_provenance": dict(run_provenance),
        "findings": findings,
        "limitations": limitations,
    }


def render_report(summary: Mapping[str, Any]) -> str:
    dataset = summary["dataset"]
    slices = dataset["slices"]
    value_layer = summary["value_layer"]
    criterion_a = summary["criterion_a_online_slice"]
    criterion_b = summary["criterion_b_local_subset"]
    criterion_c = summary["criterion_c_unit_honesty"]
    criterion_d = summary["criterion_d_basis_honesty"]
    unfreeze = summary["criterion_c_unfreeze"]
    reconcile = summary["criterion_e_row_reconciliation"]
    audit = summary["group_overlap_audit"]
    lines: list[str] = []

    def add(text: str = "") -> None:
        lines.append(text)

    add("# W17-3 在线黏度切片入库：viscosity_v02")
    add("")
    add("本报告由 probes/build_viscosity_v02.py 从 probes/viscosity_v02_summary.json 逐字渲染；")
    add("判据在跑前冻结于 probes/build_viscosity_v02_prereg.json。本臂只建表与计数：不拟合模型、不产 R2/MAE。")
    add("")
    add("## 1 数据源与三层口径")
    add("")
    add("- 目录层：NIST/TRC ThermoML JSON 检索 API（" + str(summary["api"]["endpoint"]) + "），三条检索词分别取全库与两个黏度切片。")
    add("- 数值层：同源 ThermoML XML（" + "https://trc.nist.gov/ThermoML/{doi}.xml" + "）里的 NumValues 观测行。")
    add("- 解冻层：本地 176 行运动黏度 kappa(T) 用 data/density_v01.csv 的 rho(T) 反解 eta = kappa * rho。")
    add(
        "- 在线行数口径：unknown（JSON API 只给记录级元数据与 data_summary 计数，不含数值行）；"
        "一切覆盖率一律以记录数或 InChIKey 数计，绝不相除。"
    )
    add("")
    add("## 2 目录层（判据 A）")
    add("")
    add("- 全库检索词 * 的在线 size 是 {} 条记录。".format(dataset["total_records"]["size_records"]))
    add("")
    add("| 切片 | size 记录数 | 抓取页数 | 抓到记录数 | 唯一 DOI | 结构化命中记录数 |")
    add("|---|---:|---:|---:|---:|---:|")
    for slug in (PA_S_SLUG, KINEMATIC_SLUG):
        slice_dataset = slices[slug]
        add(
            "| {} | {} 条记录 | {} | {} 条记录 | {} | {} 条记录 |".format(
                slice_dataset["query"],
                slice_dataset["size_records"],
                slice_dataset["pages_fetched"],
                slice_dataset["records_collected"],
                slice_dataset["unique_dois"],
                slice_dataset["records_with_structured_property_name"],
            )
        )
    add("")
    add(
        "- 分页是 0 基的（pageNum 起于 0，否则最前 100 条记录永久漏掉）；两个切片都逐位复现 size、"
        "抓到记录数 == size、DOI 唯一、零失败页。"
    )
    add(
        "- 两个切片 DOI 并集 {} 条记录，交集 {} 条记录。".format(
            criterion_a["doi_union_records"], criterion_a["doi_intersection_records"]
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
    add("## 3 单位诚实三档（判据 C）")
    add("")
    add("- tier1 单位换算表（显式列全，不在表里即 unit_rejected）：")
    for property_name in (PA_S_PROPERTY, KINEMATIC_PROPERTY):
        table = criterion_c["unit_table"][property_name]
        add(
            "  - {} -> {}：{}".format(
                property_name,
                PROPERTY_SI_UNIT[property_name],
                "、".join(f"{unit}={factor:g}" for unit, factor in table.items()),
            )
        )
    add(f"- tier2 温度区间 ({MIN_T_K}, {MAX_T_K}) K；tier3 数值区间 Pa*s (1e-6, 1e3) / m2/s (1e-10, 1e-3)。")
    add(
        "- 分档账本：命中属性名总观测 {} 条 = 纯组分接受 {} 条 + 多组分另册 {} 条 + 未识别单位 {} 条 + "
        "超范围温度 {} 条 + 非法值 {} 条。".format(
            value_layer["total_named_viscosity_rows"],
            value_layer["ledger"].get("accepted_pure_rows", 0),
            value_layer["ledger"].get("multi_component_deferred_rows", 0),
            value_layer["ledger"].get("unit_rejected_rows", 0),
            value_layer["ledger"].get("temperature_rejected_rows", 0),
            value_layer["ledger"].get("value_rejected_rows", 0),
        )
    )
    add("- 未识别单位逐条列账（不静默丢）：")
    if value_layer["unrecognized_units"]:
        for entry in value_layer["unrecognized_units"]:
            add(
                "  - {} / {}：{} 条".format(
                    entry["property_name"], entry["property_unit_raw"], entry["count"]
                )
            )
    else:
        add("  - 无（全部单位都在换算表里）。")
    add(
        "- 判据 C：{} 条违反，允许 {}，判 {}。".format(
            criterion_c["n_violations"],
            criterion_c["allowed_violations"],
            "通过" if criterion_c["passed"] else "未通过",
        )
    )
    add("")
    add("## 4 本地 ⊆ 在线（判据 B）")
    add("")
    add(
        "- 本地含黏度 DOI {} 个（来源 {}）逐个命中在线并集：命中 {} 个，缺 {} 个。".format(
            criterion_b["local_doi_count"],
            criterion_b["local_source"]["path"],
            criterion_b["hit_count"],
            len(criterion_b["missing_dois"]),
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
    add("## 5 主表与双口径清点（判据 D）")
    add("")
    dual = criterion_d["dual_basis_counts"]
    add(
        "- 在线记录数（切片口径）：Pa*s 切片 {} 条记录、kinematic 切片 {} 条记录、并集 {} 条记录。".format(
            dual["online_pa_s_slice_records"],
            dual["online_kinematic_slice_records"],
            dual["online_union_records"],
        )
    )
    add(
        "- 数值层观测行数：{} 行（唯一 InChIKey {} 个）。".format(
            dual["raw_named_rows"], dual["raw_named_inchikeys"]
        )
    )
    add(
        "- 主表 viscosity_v02 行数：{} 行（唯一 InChIKey {} 个）= Pa*s 直测 {} 行 + 运动黏度反解 {} 行。".format(
            dual["viscosity_v02_rows"],
            dual["viscosity_v02_inchikeys"],
            dual["pa_s_measured_rows"],
            dual["kinematic_converted_rows"],
        )
    )
    add("- 多组分另册登记：{} 行（未做溶质/溶剂角色拆分前不入主表）。".format(dual["multi_component_deferred_rows"]))
    add("- " + criterion_d["size_unit_statement"])
    add("- " + criterion_d["value_basis_statement"])
    add("- 在线数据行数：unknown —— " + criterion_d["online_row_count_reason"])
    add(
        "- 判据 D：{} 条违反，允许 {}，判 {}。".format(
            criterion_d["n_violations"],
            criterion_d["allowed_violations"],
            "通过" if criterion_d["passed"] else "未通过",
        )
    )
    add("")
    add("## 6 与本地 Pa*s 观测逐行对账（判据 E）")
    add("")
    add(
        "- 本地 Pa*s 观测 {} 行（data/processed/viscosity_observations_thermoml.csv）与在线收割逐行比对："
        "命中 {} 行，未命中 {} 行。".format(
            reconcile["local_rows"], reconcile["matched_local_rows"], reconcile["unmatched_local_rows"]
        )
    )
    add(
        "- 对账键 = 同 DOI + 同 InChIKey + 同温度 + 同源行号；重复行只标 source_priority"
        "（online_duplicate_of_local / online_new），不合并、不平均。"
    )
    add("")
    add("## 7 运动黏度解冻（判据 C 解冻）")
    add("")
    add("- 目标：本地运动黏度 {} 行（{} 个化合物）。".format(unfreeze["local_rows"], unfreeze["local_keys"]))
    add(
        "- exact（|dT| <= {} K）配到密度：{} 行。".format(unfreeze["exact_tolerance_k"], unfreeze["exact_rows"])
    )
    add(
        "- nearest（|dT| <= {} K，取最近邻）配到密度：{} 行。".format(
            unfreeze["nearest_tolerance_k"], unfreeze["nearest_rows"]
        )
    )
    add(
        "- 反解 eta = kappa * rho：{} 行；其中纯组分入主表 {} 行、多组分另册 {} 行。".format(
            unfreeze["converted_rows"], unfreeze["pooled_rows"], unfreeze["deferred_multi_component_rows"]
        )
    )
    add("- 逐行换算 provenance（换算乘子 rho、配对密度来源 DOI、配对容差）见 summary 的 per_row。")
    add(
        "- 另册口径：在线 kinematic 切片纯组分接受行 {} 行，本臂只按预注册范围反解本地 176 行"
        "（纯组分 {} 行入主表），其余纯组分运动黏度行未做换算。".format(
            value_layer["accepted_pure_kinematic_rows"], unfreeze["pooled_rows"]
        )
    )
    add("")
    add("| InChIKey | 运动黏度行数 | exact | nearest | 入主表 |")
    add("|---|---:|---:|---:|---:|")
    for key, bucket in unfreeze["by_key"].items():
        add("| {} | {} | {} | {} | {} |".format(key, bucket["rows"], bucket["exact"], bucket["nearest"], bucket["pooled"]))
    add("")
    add("## 8 联表重建 group_overlap 断言")
    add("")
    add(
        "- 在重建的联表（viscosity_v02 主表 {} 行 / {} 组）上跑 GroupKFold by InChIKey："
        "max_group_overlap = {}，断言 group_overlap == 0 {}。".format(
            audit["subset_rows"],
            audit["subset_groups"],
            audit["max_group_overlap"],
            "通过" if audit["assertion_passed"] else "未通过",
        )
    )
    add(
        "- random_row 只作泄漏参照，永不进判决：leaked_fraction = {}。".format(
            audit["random_row"]["leaked_fraction"]
        )
    )
    add("")
    add("## 9 读数与边界")
    add("")
    for item in summary["findings"]:
        add("- " + str(item))
    for item in summary["limitations"]:
        add("- " + str(item))
    add("")
    add("## 10 复现")
    add("")
    add("- 首跑：.venv\\Scripts\\python.exe probes/build_viscosity_v02.py --resolve-online")
    add("- 增量：.venv\\Scripts\\python.exe probes/build_viscosity_v02.py")
    add("- 离线核查：.venv\\Scripts\\python.exe probes/build_viscosity_v02.py --check")
    add("- 独立核验：.venv\\Scripts\\python.exe scripts/verify_viscosity_v02.py --check")
    add("- 目录层清单指纹（manifest_sha256）：" + str(dataset["manifest_sha256"]))
    add("")
    return "\n".join(lines)


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

    local_obs = read_local_observations(args.local_obs)
    local_doi_source = load_local_doi_source(args.local_coverage)
    density_rows = read_csv_rows(args.density)
    density_keys = {
        (row.get("inchikey") or "").strip()
        for row in density_rows
        if (row.get("inchikey") or "").strip()
    }

    input_digests = {
        "density_v01": {
            "path": display_path(args.density),
            "sha256": sha256_file(args.density),
            "rows": len(density_rows),
            "keys": len(density_keys),
        },
        "local_observations": {
            "path": display_path(args.local_obs),
            "sha256": sha256_file(args.local_obs),
            "rows": len(local_obs["all_rows"]),
            "pa_s_rows": len(local_obs["pa_s_rows"]),
            "kinematic_rows": len(local_obs["kinematic_rows"]),
        },
        "local_coverage_summary": {
            "path": display_path(args.local_coverage),
            "sha256": sha256_file(args.local_coverage),
            "viscosity_files": int(local_doi_source["viscosity_files"]),
            "dois": len(local_doi_source["dois"]),
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
            "slices": {
                slug: dict(fallback["dataset"]["slices"][slug])
                for slug in (PA_S_SLUG, KINEMATIC_SLUG)
            },
            "doi_union": list(fallback["dataset"]["doi_union"]),
            "doi_intersection": list(fallback["dataset"]["doi_intersection"]),
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
    dois = list(dataset["doi_union"])
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
        if fallback is None or not args.raw.is_file():
            raise ValueLayerUnavailable(
                "数值层 XML 缓存缺失，且没有可退用的已提交产物（data/processed/viscosity_v02_raw.csv）。"
            )
        value_layer = {
            "source": "committed_csv",
            "raw_rows": read_csv_rows(args.raw),
            "total_named_viscosity_rows": int(
                fallback["value_layer"]["total_named_viscosity_rows"]
            ),
            "parse_failures": list(fallback["value_layer"].get("parse_failures", [])),
            "smiles_unresolved": int(fallback["value_layer"].get("smiles_unresolved", 0)),
        }

    raw_rows = value_layer["raw_rows"]
    value_layer["total_named_viscosity_rows"] = len(raw_rows)
    value_layer["xml_status"] = xml_status
    value_layer["ledger"] = ledger_from_raw(raw_rows)
    counts = accepted_pure_counts(raw_rows)
    value_layer["accepted_pure_pa_s_rows"] = counts["pa_s"]
    value_layer["accepted_pure_kinematic_rows"] = counts["kinematic"]
    value_layer["unrecognized_units"] = unrecognized_units(raw_rows)
    value_layer["unique_keys"] = len(
        {row["inchikey"] for row in raw_rows if row["inchikey"]}
    )
    value_layer["temperature_distribution"] = temperature_distribution(raw_rows)

    reconciler = reconcile_local_pa_s(raw_rows, local_obs["pa_s_rows"])
    pairing = pair_kinematic_rows(local_obs["kinematic_rows"], density_rows)

    table_rows = main_rows_from_raw(
        raw_rows, matched_row_keys=reconciler["matched_row_keys"]
    )
    table_rows += main_rows_from_unfreeze(pairing)
    table_rows = finalize_table_rows(table_rows)
    raw_for_csv = [
        {column: row.get(column, "") for column in RAW_COLUMNS} for row in raw_rows
    ]

    table_text = csv_text(TABLE_COLUMNS, table_rows)
    raw_text = csv_text(RAW_COLUMNS, raw_for_csv)
    outputs = {
        "table": {
            "path": display_path(args.table),
            "rows": len(table_rows),
            "sha256": sha256_text(table_text),
        },
        "raw": {
            "path": display_path(args.raw),
            "rows": len(raw_for_csv),
            "sha256": sha256_text(raw_text),
        },
        "report": {"path": display_path(args.report)},
        "summary": {"path": display_path(args.summary)},
    }
    run_provenance = {
        "cache": catalog_status,
        "value_layer_source": value_layer["source"],
        "xml_status": xml_status,
        "xml_cache_dir": display_path(args.xml_cache),
        "page_sources": page_sources,
        "request_budget": {
            "limit": int(budget.limit),
            "used": int(budget.used),
            "bytes_transferred": int(budget.bytes_transferred),
        },
        "request_ledger_entries": len(ledger),
        "group_overlap_assertion": "group_overlap == 0",
    }
    run_provenance["run_telemetry"] = {
        "network_calls": int(budget.used),
        "models_fitted": 0,
        "r2_reported": 0,
        "writes_under_data": 2,
        "run_mode": "online" if online else "offline",
    }

    summary = build_summary(
        prereg=prereg,
        prereg_path=args.prereg,
        prereg_sha256=prereg_sha256,
        dataset=dataset,
        value_layer=value_layer,
        table_rows=table_rows,
        pairing=pairing,
        reconciler=reconciler,
        local_doi_source=local_doi_source,
        local_obs_counts={
            "all_rows": len(local_obs["all_rows"]),
            "pa_s_rows": len(local_obs["pa_s_rows"]),
            "kinematic_rows": len(local_obs["kinematic_rows"]),
        },
        input_digests=input_digests,
        outputs=outputs,
        run_provenance=run_provenance,
        generated_at=generated_at or utc_now(),
    )
    report = render_report(summary)
    violations = guard_violations(prereg, report, summary)
    if violations:
        raise ValueError("措辞守卫未过：" + "；".join(violations[:5]))
    return summary, report, table_rows, raw_for_csv


def print_summary(summary: Mapping[str, Any], summary_path: Path, report_path: Path) -> None:
    criterion_a = summary["criterion_a_online_slice"]
    criterion_b = summary["criterion_b_local_subset"]
    criterion_c = summary["criterion_c_unit_honesty"]
    criterion_d = summary["criterion_d_basis_honesty"]
    unfreeze = summary["criterion_c_unfreeze"]
    audit = summary["group_overlap_audit"]
    print("task          : " + summary["task"])
    print(
        "criterion A   : {} (violations {}/{})".format(
            "PASS" if criterion_a["passed"] else "FAIL",
            criterion_a["n_violations"],
            criterion_a["allowed_violations"],
        )
    )
    print(
        "criterion B   : {} (hit {}/{} local DOIs)".format(
            "PASS" if criterion_b["passed"] else "FAIL",
            criterion_b["hit_count"],
            criterion_b["local_doi_count"],
        )
    )
    print(
        "criterion C   : {} (violations {}/{})".format(
            "PASS" if criterion_c["passed"] else "FAIL",
            criterion_c["n_violations"],
            criterion_c["allowed_violations"],
        )
    )
    print(
        "criterion D   : {} (violations {}/{})".format(
            "PASS" if criterion_d["passed"] else "FAIL",
            criterion_d["n_violations"],
            criterion_d["allowed_violations"],
        )
    )
    print(
        "unfreeze      : {} exact / {} nearest / {} converted / {} pooled of {} local rows".format(
            unfreeze["exact_rows"],
            unfreeze["nearest_rows"],
            unfreeze["converted_rows"],
            unfreeze["pooled_rows"],
            unfreeze["local_rows"],
        )
    )
    print(
        "group_overlap : max {} (assertion {})".format(
            audit["max_group_overlap"],
            "PASS" if audit["assertion_passed"] else "FAIL",
        )
    )
    print("manifest sha  : {}".format(summary["dataset"]["manifest_sha256"]))
    print(f"summary       : {display_path(summary_path)}")
    print(f"report        : {display_path(report_path)}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="W17-3 在线黏度切片入库：建 data/viscosity_v02.csv（ThermoML 目录层 + XML 数值层 + rho 解冻）。"
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
    parser.add_argument("--density", type=Path, default=DEFAULT_DENSITY)
    parser.add_argument("--local-obs", type=Path, default=DEFAULT_LOCAL_OBS)
    parser.add_argument("--local-coverage", type=Path, default=DEFAULT_LOCAL_COVERAGE)
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
            problems.append("viscosity_v02.csv 与离线重算不一致")
        if not args.raw.is_file():
            problems.append(f"缺原始层：{display_path(args.raw)}")
        elif read_text_raw(args.raw) != csv_text(RAW_COLUMNS, raw_rows):
            problems.append("viscosity_v02_raw.csv 与离线重算不一致")
        for problem in problems:
            print("FAIL " + problem)
        if problems:
            return 1
        criterion_a = summary["criterion_a_online_slice"]
        unfreeze = summary["criterion_c_unfreeze"]
        print(
            "OK 离线复算一致；判据 A {}；解冻 {}/{} 行（入主表 {}）；目录层来源 {}；数值层来源 {}".format(
                "PASS" if criterion_a["passed"] else "FAIL",
                unfreeze["nearest_rows"],
                unfreeze["local_rows"],
                unfreeze["pooled_rows"],
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
