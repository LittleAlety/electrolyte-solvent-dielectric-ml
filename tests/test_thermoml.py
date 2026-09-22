from __future__ import annotations

import hashlib
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar

from electrolyte_ml.thermoml import (
    CSV_COLUMNS,
    download_url,
    parse_thermoml_bytes,
    write_normalized_csv,
)

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


class _RangeHTTPRequestHandler(BaseHTTPRequestHandler):
    body: ClassVar[bytes] = THERMOML_FIXTURE.encode("utf-8")
    requests: ClassVar[list[str | None]] = []
    user_agents: ClassVar[list[str | None]] = []

    def do_GET(self) -> None:
        self.__class__.requests.append(self.headers.get("Range"))
        self.__class__.user_agents.append(self.headers.get("User-Agent"))
        range_header = self.headers.get("Range")
        start = 0
        status = 200
        if range_header and range_header.startswith("bytes="):
            start = int(range_header.removeprefix("bytes=").split("-", 1)[0])
            status = 206

        payload = self.body[start:]
        self.send_response(status)
        self.send_header("Content-Type", "application/xml")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Accept-Ranges", "bytes")
        if status == 206:
            self.send_header(
                "Content-Range",
                f"bytes {start}-{len(self.body) - 1}/{len(self.body)}",
            )
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:
        return


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

    def test_keeps_component_specific_composition_variables(self) -> None:
        rows = parse_thermoml_bytes(MIXTURE_FIXTURE.encode("utf-8"))
        components = json.loads(rows[0]["components_json"])

        self.assertEqual(rows[0]["temperature_value"], "298.15")
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


class DownloadTests(unittest.TestCase):
    def setUp(self) -> None:
        _RangeHTTPRequestHandler.requests = []
        _RangeHTTPRequestHandler.user_agents = []
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
        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "sample.xml"
            partial_path = destination.with_name(destination.name + ".part")
            partial_path.write_bytes(_RangeHTTPRequestHandler.body[:32])

            result = download_url(self.url, destination, resume=True)

            self.assertEqual(result.status, "resumed")
            self.assertEqual(destination.read_bytes(), _RangeHTTPRequestHandler.body)
            self.assertEqual(_RangeHTTPRequestHandler.requests, ["bytes=32-"])

    def test_dry_run_does_not_write_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "sample.xml"

            result = download_url(self.url, destination, dry_run=True)

            self.assertEqual(result.status, "planned")
            self.assertFalse(destination.exists())
            self.assertEqual(_RangeHTTPRequestHandler.requests, [])


if __name__ == "__main__":
    unittest.main()
