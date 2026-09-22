from __future__ import annotations

import concurrent.futures
import hashlib
import json
import multiprocessing
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar
from unittest.mock import patch

from electrolyte_ml.thermoml import (
    CSV_COLUMNS,
    DownloadError,
    _destination_lock,
    build_provenance,
    download_url,
    parse_thermoml_bytes,
    write_normalized_csv,
)
from scripts.fetch_thermoml import _destinations_for_urls

THERMOML_FIXTURE = """\
<?xml version="1.0" encoding="UTF-8"?>
<DataReport xmlns="http://www.iupac.org/namespaces/ThermoML">
  <Version>
    <nVersionMajor>2</nVersionMajor>
    <nVersionMinor>0</nVersionMinor>
  </Version>
  <Citation>
    <sTitle>ThermoML parser fixture</sTitle>
    <sDOI>10.0000/fixture</sDOI>
  </Citation>
  <Compound>
    <RegNum>
      <nOrgNum>1</nOrgNum>
    </RegNum>
    <sStandardInChI>InChI=1S/C2H6O/c1-2-3/h3H,2H2,1H3</sStandardInChI>
    <sStandardInChIKey>LFQSCWFLJHTTHZ-UHFFFAOYSA-N</sStandardInChIKey>
    <sCommonName>ethanol</sCommonName>
    <sFormulaMolec>C2H6O</sFormulaMolec>
  </Compound>
  <Compound>
    <RegNum>
      <nOrgNum>2</nOrgNum>
    </RegNum>
    <sStandardInChI>InChI=1S/H2O/h1H2</sStandardInChI>
    <sStandardInChIKey>XLYOFNOQVPJJNP-UHFFFAOYSA-N</sStandardInChIKey>
    <sCommonName>water</sCommonName>
    <sFormulaMolec>H2O</sFormulaMolec>
  </Compound>
  <PureOrMixtureData>
    <nPureOrMixtureDataNumber>1</nPureOrMixtureDataNumber>
    <Component>
      <RegNum>
        <nOrgNum>1</nOrgNum>
      </RegNum>
      <nSampleNm>1</nSampleNm>
    </Component>
    <Component>
      <RegNum>
        <nOrgNum>2</nOrgNum>
      </RegNum>
      <nSampleNm>1</nSampleNm>
    </Component>
    <Property>
      <nPropNumber>1</nPropNumber>
      <Property-MethodID>
        <PropertyGroup>
          <RefractionSurfaceTensionSoundSpeed>
            <ePropName>Relative permittivity at zero frequency</ePropName>
            <sMethodName>dielectric analyzer</sMethodName>
          </RefractionSurfaceTensionSoundSpeed>
        </PropertyGroup>
      </Property-MethodID>
      <PropPhaseID>
        <ePropPhase>Liquid</ePropPhase>
      </PropPhaseID>
    </Property>
    <Property>
      <nPropNumber>2</nPropNumber>
      <Property-MethodID>
        <PropertyGroup>
          <RefractionSurfaceTensionSoundSpeed>
            <ePropName>Speed of sound, m/s</ePropName>
            <sMethodName>acoustic cell</sMethodName>
          </RefractionSurfaceTensionSoundSpeed>
        </PropertyGroup>
      </Property-MethodID>
      <PropPhaseID>
        <ePropPhase>Liquid</ePropPhase>
      </PropPhaseID>
    </Property>
    <PhaseID>
      <ePhase>Liquid</ePhase>
    </PhaseID>
    <Variable>
      <nVarNumber>1</nVarNumber>
      <VariableID>
        <VariableType>
          <eTemperature>Temperature, K</eTemperature>
        </VariableType>
      </VariableID>
    </Variable>
    <Variable>
      <nVarNumber>2</nVarNumber>
      <VariableID>
        <VariableType>
          <eMiscellaneous>Frequency, MHz</eMiscellaneous>
        </VariableType>
      </VariableID>
    </Variable>
    <NumValues>
      <VariableValue>
        <nVarNumber>1</nVarNumber>
        <nVarValue>298.15</nVarValue>
        <nVarDigits>5</nVarDigits>
      </VariableValue>
      <VariableValue>
        <nVarNumber>2</nVarNumber>
        <nVarValue>1.0</nVarValue>
        <nVarDigits>2</nVarDigits>
      </VariableValue>
      <PropertyValue>
        <nPropNumber>1</nPropNumber>
        <nPropValue>12.5</nPropValue>
        <nPropDigits>3</nPropDigits>
        <CombinedUncertainty>
          <nCombExpandUncertValue>0.2</nCombExpandUncertValue>
        </CombinedUncertainty>
      </PropertyValue>
      <PropertyValue>
        <nPropNumber>2</nPropNumber>
        <nPropValue>1500.0</nPropValue>
        <nPropDigits>5</nPropDigits>
      </PropertyValue>
    </NumValues>
    <NumValues>
      <VariableValue>
        <nVarNumber>1</nVarNumber>
        <nVarValue>298.15</nVarValue>
        <nVarDigits>5</nVarDigits>
      </VariableValue>
      <VariableValue>
        <nVarNumber>2</nVarNumber>
        <nVarValue>1.0</nVarValue>
        <nVarDigits>2</nVarDigits>
      </VariableValue>
      <PropertyValue>
        <nPropNumber>1</nPropNumber>
        <nPropValue>12.5</nPropValue>
        <nPropDigits>3</nPropDigits>
      </PropertyValue>
    </NumValues>
    <NumValues>
      <PropertyValue>
        <nPropNumber>1</nPropNumber>
        <nPropValue>20.0</nPropValue>
        <nPropDigits>3</nPropDigits>
      </PropertyValue>
    </NumValues>
  </PureOrMixtureData>
</DataReport>
"""

MIXTURE_FIXTURE = """\
<?xml version="1.0" encoding="UTF-8"?>
<DataReport xmlns="http://www.iupac.org/namespaces/ThermoML">
  <Version>
    <nVersionMajor>2</nVersionMajor>
    <nVersionMinor>0</nVersionMinor>
  </Version>
  <Citation>
    <sTitle>Mixture fixture</sTitle>
    <sDOI>10.0000/mixture</sDOI>
  </Citation>
  <Compound>
    <RegNum><nOrgNum>1</nOrgNum></RegNum>
    <sStandardInChI>InChI=1S/C2H6O/c1-2-3/h3H,2H2,1H3</sStandardInChI>
    <sStandardInChIKey>LFQSCWFLJHTTHZ-UHFFFAOYSA-N</sStandardInChIKey>
    <sCommonName>ethanol</sCommonName>
    <sFormulaMolec>C2H6O</sFormulaMolec>
  </Compound>
  <Compound>
    <RegNum><nOrgNum>2</nOrgNum></RegNum>
    <sStandardInChI>InChI=1S/H2O/h1H2</sStandardInChI>
    <sStandardInChIKey>XLYOFNOQVPJJNP-UHFFFAOYSA-N</sStandardInChIKey>
    <sCommonName>water</sCommonName>
    <sFormulaMolec>H2O</sFormulaMolec>
  </Compound>
  <PureOrMixtureData>
    <nPureOrMixtureDataNumber>1</nPureOrMixtureDataNumber>
    <Component>
      <RegNum><nOrgNum>1</nOrgNum></RegNum>
      <nSampleNm>1</nSampleNm>
    </Component>
    <Component>
      <RegNum><nOrgNum>2</nOrgNum></RegNum>
      <nSampleNm>1</nSampleNm>
    </Component>
    <Property>
      <nPropNumber>1</nPropNumber>
      <Property-MethodID>
        <PropertyGroup>
          <RefractionSurfaceTensionSoundSpeed>
            <ePropName>Relative permittivity at zero frequency</ePropName>
          </RefractionSurfaceTensionSoundSpeed>
        </PropertyGroup>
      </Property-MethodID>
    </Property>
    <Constraint>
      <nConstraintNumber>1</nConstraintNumber>
      <ConstraintID>
        <ConstraintType>
          <eMiscellaneous>Frequency, MHz</eMiscellaneous>
        </ConstraintType>
      </ConstraintID>
      <nConstraintValue>385</nConstraintValue>
      <nConstrDigits>3</nConstrDigits>
    </Constraint>
    <Variable>
      <nVarNumber>1</nVarNumber>
      <VariableID>
        <VariableType><eTemperature>Temperature, K</eTemperature></VariableType>
      </VariableID>
    </Variable>
    <Variable>
      <nVarNumber>2</nVarNumber>
      <VariableID>
        <VariableType>
          <eComponentComposition>Mole fraction</eComponentComposition>
        </VariableType>
        <RegNum><nOrgNum>1</nOrgNum></RegNum>
      </VariableID>
    </Variable>
    <Variable>
      <nVarNumber>2</nVarNumber>
      <VariableID>
        <VariableType>
          <eComponentComposition>Mole fraction</eComponentComposition>
        </VariableType>
        <RegNum><nOrgNum>2</nOrgNum></RegNum>
      </VariableID>
    </Variable>
    <NumValues>
      <VariableValue>
        <nVarNumber>1</nVarNumber>
        <nVarValue>298.15</nVarValue>
        <nVarDigits>5</nVarDigits>
      </VariableValue>
      <VariableValue>
        <nVarNumber>2</nVarNumber>
        <nVarValue>0.2</nVarValue>
        <nVarDigits>1</nVarDigits>
      </VariableValue>
      <VariableValue>
        <nVarNumber>2</nVarNumber>
        <nVarValue>0.8</nVarValue>
        <nVarDigits>1</nVarDigits>
      </VariableValue>
      <PropertyValue>
        <nPropNumber>1</nPropNumber>
        <nPropValue>55.1</nPropValue>
        <nPropDigits>3</nPropDigits>
      </PropertyValue>
    </NumValues>
  </PureOrMixtureData>
</DataReport>
"""

UNCERTAINTY_FIXTURE = """\
<?xml version="1.0" encoding="UTF-8"?>
<DataReport xmlns="http://www.iupac.org/namespaces/ThermoML">
  <Version>
    <nVersionMajor>2</nVersionMajor>
    <nVersionMinor>0</nVersionMinor>
  </Version>
  <Citation>
    <sTitle>Uncertainty fixture</sTitle>
    <sDOI>10.0000/uncertainty</sDOI>
  </Citation>
  <PureOrMixtureData>
    <nPureOrMixtureDataNumber>1</nPureOrMixtureDataNumber>
    <Property>
      <nPropNumber>1</nPropNumber>
      <Property-MethodID>
        <PropertyGroup>
          <RefractionSurfaceTensionSoundSpeed>
            <ePropName>Property one</ePropName>
          </RefractionSurfaceTensionSoundSpeed>
        </PropertyGroup>
        <CombinedUncertainty>
          <nCombUncertLevOfConfid>95</nCombUncertLevOfConfid>
        </CombinedUncertainty>
      </Property-MethodID>
    </Property>
    <Property>
      <nPropNumber>2</nPropNumber>
      <Property-MethodID>
        <PropertyGroup>
          <RefractionSurfaceTensionSoundSpeed>
            <ePropName>Property two</ePropName>
          </RefractionSurfaceTensionSoundSpeed>
        </PropertyGroup>
        <CombinedUncertainty>
          <nCombUncertLevOfConfid>99</nCombUncertLevOfConfid>
        </CombinedUncertainty>
      </Property-MethodID>
    </Property>
    <Property>
      <nPropNumber>3</nPropNumber>
      <Property-MethodID>
        <PropertyGroup>
          <RefractionSurfaceTensionSoundSpeed>
            <ePropName>Property three</ePropName>
          </RefractionSurfaceTensionSoundSpeed>
        </PropertyGroup>
      </Property-MethodID>
    </Property>
    <Property>
      <nPropNumber>4</nPropNumber>
      <Property-MethodID>
        <PropertyGroup>
          <RefractionSurfaceTensionSoundSpeed>
            <ePropName>Property four</ePropName>
          </RefractionSurfaceTensionSoundSpeed>
        </PropertyGroup>
      </Property-MethodID>
    </Property>
    <Property>
      <nPropNumber>5</nPropNumber>
      <Property-MethodID>
        <PropertyGroup>
          <RefractionSurfaceTensionSoundSpeed>
            <ePropName>Property five</ePropName>
          </RefractionSurfaceTensionSoundSpeed>
        </PropertyGroup>
      </Property-MethodID>
    </Property>
    <NumValues>
      <PropertyValue>
        <nPropNumber>1</nPropNumber>
        <nPropValue>1.0</nPropValue>
        <CombinedUncertainty>
          <nCombExpandUncertValue>0.2</nCombExpandUncertValue>
        </CombinedUncertainty>
      </PropertyValue>
      <PropertyValue>
        <nPropNumber>2</nPropNumber>
        <nPropValue>2.0</nPropValue>
        <CombinedUncertainty>
          <nCombExpandUncertValue>0.3</nCombExpandUncertValue>
        </CombinedUncertainty>
      </PropertyValue>
      <PropertyValue>
        <nPropNumber>3</nPropNumber>
        <nPropValue>3.0</nPropValue>
        <CombinedUncertainty>
          <nCombExpandUncertValue>0.4</nCombExpandUncertValue>
        </CombinedUncertainty>
      </PropertyValue>
      <PropertyValue>
        <nPropNumber>4</nPropNumber>
        <nPropValue>4.0</nPropValue>
        <CombinedUncertainty>
          <nCombStdUncertValue>0.05</nCombStdUncertValue>
        </CombinedUncertainty>
      </PropertyValue>
      <PropertyValue>
        <nPropNumber>5</nPropNumber>
        <nPropValue>5.0</nPropValue>
      </PropertyValue>
    </NumValues>
  </PureOrMixtureData>
</DataReport>
"""


class _RangeHTTPRequestHandler(BaseHTTPRequestHandler):
    body: ClassVar[bytes] = THERMOML_FIXTURE.encode("utf-8")
    etag: ClassVar[str | None] = None
    last_modified: ClassVar[str | None] = None
    range_total_delta: ClassVar[int] = 0
    not_satisfiable: ClassVar[bool] = False
    ignore_if_range: ClassVar[bool] = False
    response_delay: ClassVar[float] = 0
    fail_full_once: ClassVar[bool] = False
    response_last_modified: ClassVar[str | None] = None
    requests: ClassVar[list[str | None]] = []
    if_ranges: ClassVar[list[str | None]] = []
    user_agents: ClassVar[list[str | None]] = []

    def do_GET(self) -> None:
        self.__class__.requests.append(self.headers.get("Range"))
        self.__class__.if_ranges.append(self.headers.get("If-Range"))
        self.__class__.user_agents.append(self.headers.get("User-Agent"))
        range_header = self.headers.get("Range")
        if_range = self.headers.get("If-Range")
        if self.response_delay:
            time.sleep(self.response_delay)
        start = 0
        status = 200
        if range_header and range_header.startswith("bytes="):
            start = int(range_header.removeprefix("bytes=").split("-", 1)[0])
            if self.not_satisfiable:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{len(self.body)}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            current_validators = {
                value for value in (self.etag, self.last_modified) if value
            }
            if self.ignore_if_range or not if_range or if_range in current_validators:
                status = 206
            else:
                start = 0

        payload = self.body[start:]
        declared_length = len(payload)
        response_payload = payload
        if status == 200 and self.fail_full_once:
            self.__class__.fail_full_once = False
            response_payload = payload[:16]
        self.send_response(status)
        self.send_header("Content-Type", "application/xml")
        self.send_header("Content-Length", str(declared_length))
        self.send_header("Accept-Ranges", "bytes")
        if self.etag:
            self.send_header("ETag", self.etag)
        response_last_modified = self.response_last_modified or self.last_modified
        if response_last_modified:
            self.send_header("Last-Modified", response_last_modified)
        if status == 206:
            self.send_header(
                "Content-Range",
                (
                    f"bytes {start}-{len(self.body) - 1}/"
                    f"{len(self.body) + self.range_total_delta}"
                ),
            )
        self.end_headers()
        self.wfile.write(response_payload)

    def log_message(self, format: str, *args: object) -> None:
        return


def _download_worker(
    url: str,
    destination: Path,
    start_event: object,
    result_queue: object,
) -> None:
    start_event.wait()
    try:
        result = download_url(url, destination, resume=True)
    except Exception as exc:  # noqa: BLE001 - propagate failures to the parent test
        result_queue.put(("error", type(exc).__name__, str(exc)))
        return
    result_queue.put(("ok", result.status))


def _partial_metadata(
    url: str,
    partial: bytes,
    *,
    total_size: int,
    etag: str | None = None,
    last_modified: str | None = None,
) -> dict[str, object]:
    return {
        "url": url,
        "etag": etag,
        "last_modified": last_modified,
        "total_size": total_size,
        "sha256": hashlib.sha256(partial).hexdigest(),
        "size_bytes": len(partial),
    }


class ParseThermoMLTests(unittest.TestCase):
    def test_parses_namespaced_multiple_properties_and_dielectric_candidate(self) -> None:
        rows = parse_thermoml_bytes(
            THERMOML_FIXTURE.encode("utf-8"),
            source_name="fixture.xml",
            source_url="https://example.test/fixture.xml",
            source_sha256="abc123",
            retrieved_at="2026-09-22T00:00:00Z",
        )

        self.assertEqual(len(rows), 4)
        self.assertEqual(set(rows[0]), set(CSV_COLUMNS))
        self.assertEqual(rows[0]["doi"], "10.0000/fixture")
        self.assertEqual(rows[0]["component_count"], "2")
        self.assertEqual(rows[0]["primary_compound_name"], "ethanol")
        self.assertEqual(rows[0]["primary_compound_formula"], "C2H6O")
        self.assertEqual(
            rows[0]["primary_compound_inchi_key"],
            "LFQSCWFLJHTTHZ-UHFFFAOYSA-N",
        )
        self.assertIn('"common_name":"water"', rows[0]["components_json"])
        self.assertEqual(rows[0]["property_name"], "Relative permittivity at zero frequency")
        self.assertEqual(rows[0]["property_unit"], "")
        self.assertEqual(rows[0]["temperature_value"], "298.15")
        self.assertEqual(rows[0]["temperature_unit"], "K")
        self.assertEqual(rows[0]["frequency_value"], "1.0")
        self.assertEqual(rows[0]["frequency_unit"], "MHz")
        self.assertEqual(rows[0]["phase"], "Liquid")
        self.assertEqual(rows[0]["is_dielectric"], "true")
        self.assertEqual(rows[0]["dielectric_kind"], "static_or_zero_frequency")
        self.assertEqual(rows[1]["property_name"], "Speed of sound, m/s")
        self.assertEqual(rows[1]["property_unit"], "m/s")
        self.assertEqual(rows[1]["is_dielectric"], "false")

    def test_keeps_duplicate_rows_and_missing_temperature_and_frequency(self) -> None:
        rows = parse_thermoml_bytes(THERMOML_FIXTURE.encode("utf-8"))

        self.assertEqual(
            [rows[0]["property_value"], rows[2]["property_value"]],
            ["12.5", "12.5"],
        )
        self.assertNotEqual(rows[0]["source_row_index"], rows[2]["source_row_index"])
        self.assertEqual(rows[3]["temperature_value"], "")
        self.assertEqual(rows[3]["temperature_unit"], "")
        self.assertEqual(rows[3]["frequency_value"], "")
        self.assertEqual(rows[3]["frequency_unit"], "")

    def test_preserves_original_property_value_and_uncertainty(self) -> None:
        rows = parse_thermoml_bytes(THERMOML_FIXTURE.encode("utf-8"))

        self.assertEqual(rows[0]["property_value"], "12.5")
        self.assertEqual(rows[0]["property_value_digits"], "3")
        self.assertEqual(rows[0]["property_uncertainty"], "0.2")

    def test_preserves_uncertainty_kind_and_confidence_level(self) -> None:
        rows = parse_thermoml_bytes(UNCERTAINTY_FIXTURE.encode("utf-8"))

        self.assertEqual(
            [row["property_uncertainty"] for row in rows],
            ["0.2", "0.3", "0.4", "0.05", ""],
        )
        self.assertEqual(
            [row["property_uncertainty_kind"] for row in rows],
            ["expanded", "expanded", "expanded", "standard", ""],
        )
        self.assertEqual(
            [row["property_uncertainty_confidence_level"] for row in rows],
            ["95", "99", "", "", ""],
        )

    def test_keeps_component_specific_composition_variables(self) -> None:
        rows = parse_thermoml_bytes(MIXTURE_FIXTURE.encode("utf-8"))
        components = json.loads(rows[0]["components_json"])

        self.assertEqual(rows[0]["temperature_value"], "298.15")
        self.assertEqual(rows[0]["frequency_value"], "385")
        self.assertEqual(rows[0]["frequency_unit"], "MHz")
        self.assertEqual(components[0]["common_name"], "ethanol")
        self.assertEqual(components[0]["composition"][0]["value"], "0.2")
        self.assertEqual(components[1]["common_name"], "water")
        self.assertEqual(components[1]["composition"][0]["value"], "0.8")
        self.assertIn('"value":"0.8"', rows[0]["variables_json"])


class OutputContractTests(unittest.TestCase):
    def test_normalized_csv_uses_the_stable_column_order(self) -> None:
        rows = parse_thermoml_bytes(THERMOML_FIXTURE.encode("utf-8"))
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "normalized.csv"
            write_normalized_csv(rows, output_path)
            header = output_path.read_text(encoding="utf-8").splitlines()[0]

        self.assertEqual(header, ",".join(CSV_COLUMNS))

    def test_provenance_uses_current_schema_version_and_columns(self) -> None:
        provenance = build_provenance([], [])

        self.assertEqual(provenance["schema_version"], 2)
        self.assertEqual(provenance["columns"], list(CSV_COLUMNS))


class DestinationLockTests(unittest.TestCase):
    def test_existing_lock_file_without_owner_is_reusable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            lock_path = Path(temp_dir) / "sample.xml.lock"
            lock_path.write_text("stale bytes\n", encoding="utf-8")

            with _destination_lock(lock_path, timeout=0.2):
                self.assertTrue(lock_path.exists())

            self.assertTrue(lock_path.exists())

    def test_lock_creation_error_is_wrapped_without_leaking(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            lock_path = Path(temp_dir) / "sample.xml.lock"
            with patch(
                "electrolyte_ml.thermoml.os.open",
                side_effect=PermissionError("denied"),
            ), self.assertRaises(DownloadError), _destination_lock(
                lock_path, timeout=0.2
            ):
                pass

            with _destination_lock(lock_path, timeout=0.2):
                self.assertTrue(lock_path.exists())

    def test_lock_write_error_releases_lock(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            lock_path = Path(temp_dir) / "sample.xml.lock"
            with patch(
                "electrolyte_ml.thermoml.os.write",
                side_effect=OSError("write failed"),
            ), self.assertRaises(DownloadError), _destination_lock(
                lock_path, timeout=0.2
            ):
                pass

            with _destination_lock(lock_path, timeout=0.2):
                self.assertTrue(lock_path.exists())


class DownloadTests(unittest.TestCase):
    def setUp(self) -> None:
        _RangeHTTPRequestHandler.body = THERMOML_FIXTURE.encode("utf-8")
        _RangeHTTPRequestHandler.requests = []
        _RangeHTTPRequestHandler.if_ranges = []
        _RangeHTTPRequestHandler.user_agents = []
        _RangeHTTPRequestHandler.etag = None
        _RangeHTTPRequestHandler.last_modified = None
        _RangeHTTPRequestHandler.range_total_delta = 0
        _RangeHTTPRequestHandler.not_satisfiable = False
        _RangeHTTPRequestHandler.ignore_if_range = False
        _RangeHTTPRequestHandler.response_delay = 0
        _RangeHTTPRequestHandler.fail_full_once = False
        _RangeHTTPRequestHandler.response_last_modified = None
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _RangeHTTPRequestHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}/sample.xml"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def test_download_records_provenance_and_skips_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "sample.xml"
            first = download_url(self.url, destination)
            second = download_url(self.url, destination)
            metadata = json.loads(
                destination.with_name(destination.name + ".meta.json").read_text(
                    encoding="utf-8"
                )
            )

            self.assertEqual(first.status, "downloaded")
            self.assertEqual(second.status, "skipped")
            self.assertEqual(destination.read_bytes(), _RangeHTTPRequestHandler.body)
            self.assertEqual(metadata["url"], self.url)
            self.assertEqual(
                metadata["sha256"],
                hashlib.sha256(_RangeHTTPRequestHandler.body).hexdigest(),
            )
            self.assertTrue(metadata["retrieved_at"].endswith("Z"))
            self.assertEqual(len(_RangeHTTPRequestHandler.requests), 1)
            self.assertTrue(
                _RangeHTTPRequestHandler.user_agents[0].startswith("electrolyte-ml/")
            )

    def test_download_resumes_partial_file(self) -> None:
        _RangeHTTPRequestHandler.etag = '"v1"'
        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "sample.xml"
            partial_path = destination.with_name(destination.name + ".part")
            partial_path.write_bytes(_RangeHTTPRequestHandler.body[:32])
            partial_path.with_name(partial_path.name + ".meta.json").write_text(
                json.dumps(
                    _partial_metadata(
                        self.url,
                        _RangeHTTPRequestHandler.body[:32],
                        total_size=len(_RangeHTTPRequestHandler.body),
                        etag='"v1"',
                    )
                ),
                encoding="utf-8",
            )

            result = download_url(self.url, destination, resume=True)

            self.assertEqual(result.status, "resumed")
            self.assertEqual(destination.read_bytes(), _RangeHTTPRequestHandler.body)
            self.assertEqual(_RangeHTTPRequestHandler.requests, ["bytes=32-"])

    def test_resume_revalidates_remote_etag_before_appending(self) -> None:
        original_body = b"old-version-" + b"a" * 32
        new_body = b"new-version-" + b"b" * 32
        _RangeHTTPRequestHandler.body = new_body
        _RangeHTTPRequestHandler.etag = '"v2"'
        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "sample.xml"
            partial_path = destination.with_name(destination.name + ".part")
            partial_path.write_bytes(original_body[:16])
            partial_path.with_name(partial_path.name + ".meta.json").write_text(
                json.dumps(
                    _partial_metadata(
                        self.url,
                        original_body[:16],
                        total_size=len(original_body),
                        etag='"v1"',
                    )
                ),
                encoding="utf-8",
            )

            result = download_url(self.url, destination, resume=True)

            self.assertEqual(result.status, "downloaded")
            self.assertEqual(destination.read_bytes(), new_body)
            self.assertEqual(_RangeHTTPRequestHandler.requests, ["bytes=16-"])
            self.assertEqual(_RangeHTTPRequestHandler.if_ranges, ['"v1"'])

    def test_resume_uses_last_modified_when_etag_is_weak(self) -> None:
        weak_etag = 'W/"nist-style-validator"'
        last_modified = "Tue, 22 Sep 2026 03:02:16 GMT"
        _RangeHTTPRequestHandler.etag = weak_etag
        _RangeHTTPRequestHandler.last_modified = last_modified
        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "sample.xml"
            partial_path = destination.with_name(destination.name + ".part")
            partial_path.write_bytes(_RangeHTTPRequestHandler.body[:32])
            partial_path.with_name(partial_path.name + ".meta.json").write_text(
                json.dumps(
                    _partial_metadata(
                        self.url,
                        _RangeHTTPRequestHandler.body[:32],
                        total_size=len(_RangeHTTPRequestHandler.body),
                        etag=weak_etag,
                        last_modified=last_modified,
                    )
                ),
                encoding="utf-8",
            )

            result = download_url(self.url, destination, resume=True)

            self.assertEqual(result.status, "resumed")
            self.assertEqual(destination.read_bytes(), _RangeHTTPRequestHandler.body)
            self.assertEqual(_RangeHTTPRequestHandler.requests, ["bytes=32-"])
            self.assertEqual(
                _RangeHTTPRequestHandler.if_ranges,
                [last_modified],
            )

    def test_resume_changed_etag_in_a_206_response_falls_back_to_full_download(
        self,
    ) -> None:
        original_body = b"old-version-" + b"a" * 32
        new_body = b"new-version-" + b"b" * 32
        _RangeHTTPRequestHandler.body = new_body
        _RangeHTTPRequestHandler.etag = '"v2"'
        _RangeHTTPRequestHandler.ignore_if_range = True
        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "sample.xml"
            partial_path = destination.with_name(destination.name + ".part")
            original_partial = original_body[:16]
            partial_path.write_bytes(original_partial)
            partial_path.with_name(partial_path.name + ".meta.json").write_text(
                json.dumps(
                    _partial_metadata(
                        self.url,
                        original_partial,
                        total_size=len(original_body),
                        etag='"v1"',
                    )
                ),
                encoding="utf-8",
            )

            result = download_url(self.url, destination, resume=True)

            self.assertEqual(result.status, "downloaded")
            self.assertEqual(destination.read_bytes(), new_body)
            self.assertEqual(_RangeHTTPRequestHandler.requests, ["bytes=16-", None])
            self.assertEqual(_RangeHTTPRequestHandler.if_ranges, ['"v1"', None])
            self.assertFalse(partial_path.exists())

    def test_weak_stored_etag_is_not_compared_to_strong_response_etag(self) -> None:
        weak_etag = 'W/"v1"'
        last_modified = "Tue, 22 Sep 2026 03:02:16 GMT"
        _RangeHTTPRequestHandler.etag = '"v1"'
        _RangeHTTPRequestHandler.last_modified = last_modified
        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "sample.xml"
            partial_path = destination.with_name(destination.name + ".part")
            partial_path.write_bytes(_RangeHTTPRequestHandler.body[:32])
            partial_path.with_name(partial_path.name + ".meta.json").write_text(
                json.dumps(
                    _partial_metadata(
                        self.url,
                        _RangeHTTPRequestHandler.body[:32],
                        total_size=len(_RangeHTTPRequestHandler.body),
                        etag=weak_etag,
                        last_modified=last_modified,
                    )
                ),
                encoding="utf-8",
            )

            result = download_url(self.url, destination, resume=True)

            self.assertEqual(result.status, "resumed")
            self.assertEqual(destination.read_bytes(), _RangeHTTPRequestHandler.body)
            self.assertEqual(_RangeHTTPRequestHandler.requests, ["bytes=32-"])
            self.assertEqual(_RangeHTTPRequestHandler.if_ranges, [last_modified])

    def test_resume_accepts_206_without_response_etag_when_using_last_modified(
        self,
    ) -> None:
        weak_etag = 'W/"v1"'
        last_modified = "Tue, 22 Sep 2026 03:02:16 GMT"
        _RangeHTTPRequestHandler.last_modified = last_modified
        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "sample.xml"
            partial_path = destination.with_name(destination.name + ".part")
            partial_path.write_bytes(_RangeHTTPRequestHandler.body[:32])
            partial_path.with_name(partial_path.name + ".meta.json").write_text(
                json.dumps(
                    _partial_metadata(
                        self.url,
                        _RangeHTTPRequestHandler.body[:32],
                        total_size=len(_RangeHTTPRequestHandler.body),
                        etag=weak_etag,
                        last_modified=last_modified,
                    )
                ),
                encoding="utf-8",
            )

            result = download_url(self.url, destination, resume=True)

            self.assertEqual(result.status, "resumed")
            self.assertEqual(destination.read_bytes(), _RangeHTTPRequestHandler.body)
            self.assertEqual(_RangeHTTPRequestHandler.requests, ["bytes=32-"])
            self.assertEqual(_RangeHTTPRequestHandler.if_ranges, [last_modified])

    def test_changed_last_modified_in_206_falls_back_to_full_download(self) -> None:
        weak_etag = 'W/"v1"'
        stored_last_modified = "Tue, 22 Sep 2026 03:02:16 GMT"
        response_last_modified = "Wed, 23 Sep 2026 03:02:16 GMT"
        _RangeHTTPRequestHandler.etag = weak_etag
        _RangeHTTPRequestHandler.last_modified = stored_last_modified
        _RangeHTTPRequestHandler.response_last_modified = response_last_modified
        _RangeHTTPRequestHandler.ignore_if_range = True
        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "sample.xml"
            partial_path = destination.with_name(destination.name + ".part")
            partial_path.write_bytes(_RangeHTTPRequestHandler.body[:32])
            partial_path.with_name(partial_path.name + ".meta.json").write_text(
                json.dumps(
                    _partial_metadata(
                        self.url,
                        _RangeHTTPRequestHandler.body[:32],
                        total_size=len(_RangeHTTPRequestHandler.body),
                        etag=weak_etag,
                        last_modified=stored_last_modified,
                    )
                ),
                encoding="utf-8",
            )

            result = download_url(self.url, destination, resume=True)

            self.assertEqual(result.status, "downloaded")
            self.assertEqual(destination.read_bytes(), _RangeHTTPRequestHandler.body)
            self.assertEqual(_RangeHTTPRequestHandler.requests, ["bytes=32-", None])
            self.assertEqual(
                _RangeHTTPRequestHandler.if_ranges,
                [stored_last_modified, None],
            )
            self.assertFalse(partial_path.exists())

    def test_resume_without_validator_restarts_from_scratch(self) -> None:
        _RangeHTTPRequestHandler.etag = '"v1"'
        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "sample.xml"
            partial_path = destination.with_name(destination.name + ".part")
            partial_path.write_bytes(_RangeHTTPRequestHandler.body[:32])

            result = download_url(self.url, destination, resume=True)

            self.assertEqual(result.status, "downloaded")
            self.assertEqual(destination.read_bytes(), _RangeHTTPRequestHandler.body)
            self.assertEqual(_RangeHTTPRequestHandler.requests, [None])
            self.assertEqual(_RangeHTTPRequestHandler.if_ranges, [None])

    def test_resume_rejects_content_range_with_different_total_size(self) -> None:
        _RangeHTTPRequestHandler.etag = '"v1"'
        _RangeHTTPRequestHandler.range_total_delta = 1
        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "sample.xml"
            partial_path = destination.with_name(destination.name + ".part")
            original_partial = _RangeHTTPRequestHandler.body[:32]
            partial_path.write_bytes(original_partial)
            partial_path.with_name(partial_path.name + ".meta.json").write_text(
                json.dumps(
                    _partial_metadata(
                        self.url,
                        original_partial,
                        total_size=len(_RangeHTTPRequestHandler.body),
                        etag='"v1"',
                    )
                ),
                encoding="utf-8",
            )

            with self.assertRaises(DownloadError):
                download_url(self.url, destination, resume=True)

            self.assertEqual(partial_path.read_bytes(), original_partial)
            self.assertFalse(destination.exists())

    def test_resume_recovers_from_http_416_with_full_download(self) -> None:
        _RangeHTTPRequestHandler.etag = '"v1"'
        _RangeHTTPRequestHandler.not_satisfiable = True
        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "sample.xml"
            partial_path = destination.with_name(destination.name + ".part")
            partial_path.write_bytes(_RangeHTTPRequestHandler.body[:32])
            partial_path.with_name(partial_path.name + ".meta.json").write_text(
                json.dumps(
                    _partial_metadata(
                        self.url,
                        _RangeHTTPRequestHandler.body[:32],
                        total_size=len(_RangeHTTPRequestHandler.body),
                        etag='"v1"',
                    )
                ),
                encoding="utf-8",
            )

            result = download_url(self.url, destination, resume=True)

            self.assertEqual(result.status, "downloaded")
            self.assertEqual(destination.read_bytes(), _RangeHTTPRequestHandler.body)
            self.assertEqual(_RangeHTTPRequestHandler.requests, ["bytes=32-", None])
            self.assertEqual(_RangeHTTPRequestHandler.if_ranges, ['"v1"', None])

    def test_interrupted_200_fallback_retries_from_clean_generation(self) -> None:
        original_body = b"old-version-" + b"a" * 32
        new_body = b"new-version-" + b"b" * 32
        _RangeHTTPRequestHandler.body = new_body
        _RangeHTTPRequestHandler.etag = '"v2"'
        _RangeHTTPRequestHandler.fail_full_once = True
        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "sample.xml"
            partial_path = destination.with_name(destination.name + ".part")
            partial_metadata_path = partial_path.with_name(
                partial_path.name + ".meta.json"
            )
            original_partial = original_body[:16]
            partial_path.write_bytes(original_partial)
            partial_metadata_path.write_text(
                json.dumps(
                    {
                        "url": self.url,
                        "etag": '"v1"',
                        "total_size": len(original_body),
                        "sha256": hashlib.sha256(original_partial).hexdigest(),
                        "size_bytes": len(original_partial),
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(DownloadError):
                download_url(self.url, destination, resume=True)

            self.assertFalse(partial_path.exists())
            self.assertFalse(partial_metadata_path.exists())
            self.assertFalse(destination.exists())

            result = download_url(self.url, destination, resume=True)

            self.assertEqual(result.status, "downloaded")
            self.assertEqual(destination.read_bytes(), new_body)
            self.assertEqual(_RangeHTTPRequestHandler.requests, ["bytes=16-", None])

    def test_interrupted_416_fallback_retries_from_clean_generation(self) -> None:
        _RangeHTTPRequestHandler.etag = '"v1"'
        _RangeHTTPRequestHandler.not_satisfiable = True
        _RangeHTTPRequestHandler.fail_full_once = True
        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "sample.xml"
            partial_path = destination.with_name(destination.name + ".part")
            partial_metadata_path = partial_path.with_name(
                partial_path.name + ".meta.json"
            )
            original_partial = b"s" * 32
            partial_path.write_bytes(original_partial)
            partial_metadata_path.write_text(
                json.dumps(
                    {
                        "url": self.url,
                        "etag": '"v1"',
                        "total_size": len(_RangeHTTPRequestHandler.body),
                        "sha256": hashlib.sha256(original_partial).hexdigest(),
                        "size_bytes": len(original_partial),
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(DownloadError):
                download_url(self.url, destination, resume=True)

            self.assertFalse(partial_path.exists())
            self.assertFalse(partial_metadata_path.exists())
            self.assertFalse(destination.exists())

            _RangeHTTPRequestHandler.not_satisfiable = False
            result = download_url(self.url, destination, resume=True)

            self.assertEqual(result.status, "downloaded")
            self.assertEqual(destination.read_bytes(), _RangeHTTPRequestHandler.body)
            self.assertEqual(_RangeHTTPRequestHandler.requests, ["bytes=32-", None, None])

    def test_concurrent_threads_serialize_resume_for_one_destination(self) -> None:
        _RangeHTTPRequestHandler.etag = '"v1"'
        _RangeHTTPRequestHandler.response_delay = 0.2
        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "sample.xml"
            partial_path = destination.with_name(destination.name + ".part")
            partial_path.write_bytes(_RangeHTTPRequestHandler.body[:32])
            partial_path.with_name(partial_path.name + ".meta.json").write_text(
                json.dumps(
                    _partial_metadata(
                        self.url,
                        _RangeHTTPRequestHandler.body[:32],
                        total_size=len(_RangeHTTPRequestHandler.body),
                        etag='"v1"',
                    )
                ),
                encoding="utf-8",
            )
            barrier = threading.Barrier(2)

            def worker() -> str:
                barrier.wait()
                return download_url(self.url, destination, resume=True).status

            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                statuses = sorted(executor.map(lambda _: worker(), range(2)))

            self.assertEqual(statuses, ["resumed", "skipped"])
            self.assertEqual(destination.read_bytes(), _RangeHTTPRequestHandler.body)
            self.assertFalse(partial_path.exists())
            self.assertEqual(len(_RangeHTTPRequestHandler.requests), 1)

    def test_concurrent_processes_serialize_resume_for_one_destination(self) -> None:
        _RangeHTTPRequestHandler.etag = '"v1"'
        _RangeHTTPRequestHandler.response_delay = 0.2
        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "sample.xml"
            partial_path = destination.with_name(destination.name + ".part")
            partial_path.write_bytes(_RangeHTTPRequestHandler.body[:32])
            partial_path.with_name(partial_path.name + ".meta.json").write_text(
                json.dumps(
                    _partial_metadata(
                        self.url,
                        _RangeHTTPRequestHandler.body[:32],
                        total_size=len(_RangeHTTPRequestHandler.body),
                        etag='"v1"',
                    )
                ),
                encoding="utf-8",
            )
            context = multiprocessing.get_context("spawn")
            start_event = context.Event()
            result_queue = context.Queue()
            processes = [
                context.Process(
                    target=_download_worker,
                    args=(self.url, destination, start_event, result_queue),
                )
                for _ in range(2)
            ]

            for process in processes:
                process.start()
            start_event.set()
            for process in processes:
                process.join(timeout=15)

            results = [result_queue.get(timeout=5) for _ in processes]
            for process in processes:
                self.assertEqual(process.exitcode, 0)

            self.assertEqual(
                sorted(result[1] for result in results),
                ["resumed", "skipped"],
            )
            self.assertEqual(destination.read_bytes(), _RangeHTTPRequestHandler.body)
            self.assertFalse(partial_path.exists())
            self.assertEqual(len(_RangeHTTPRequestHandler.requests), 1)

    def test_dry_run_does_not_write_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "sample.xml"

            result = download_url(self.url, destination, dry_run=True)

            self.assertEqual(result.status, "planned")
            self.assertFalse(destination.exists())
            self.assertEqual(_RangeHTTPRequestHandler.requests, [])

    def test_duplicate_basenames_get_distinct_destinations(self) -> None:
        urls = [
            "https://example.test/10.1000/solvent.xml",
            "https://example.test/10.2000/solvent.xml",
        ]

        destinations = _destinations_for_urls(urls)

        self.assertEqual(len({str(path) for path in destinations}), 2)

    def test_destination_for_url_is_stable_across_different_batches(self) -> None:
        first_url = "https://example.test/10.1000/shared-name.xml"
        second_url = "https://example.test/10.2000/shared-name.xml"

        single_destination = _destinations_for_urls([first_url])[0]
        mixed_destinations = _destinations_for_urls([first_url, second_url])
        reversed_destinations = _destinations_for_urls([second_url, first_url])

        self.assertEqual(single_destination, mixed_destinations[0])
        self.assertEqual(single_destination, reversed_destinations[1])
        self.assertNotEqual(mixed_destinations[0], mixed_destinations[1])
        self.assertIn("10.1000", single_destination.name)
        self.assertIn("shared-name", single_destination.name)


if __name__ == "__main__":
    unittest.main()
