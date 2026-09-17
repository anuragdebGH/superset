# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
"""Pin the apispec rendering that the published OpenAPI document encodes.

``docs/static/resources/openapi.json`` is a generated artifact, so the
installed apispec release is part of its contract. These tests fail on a
release that renders schemas differently, which surfaces as a spec drift
failure in CI rather than as an obvious dependency problem.
"""

from pathlib import Path
from typing import Any

from apispec import APISpec
from apispec.ext.marshmallow import MarshmallowPlugin
from marshmallow import fields, Schema

from superset.openapi.manager import resolver
from superset.utils import json


class InnerSchema(Schema):
    name = fields.String()


class OuterSchema(Schema):
    payload = fields.Dict()
    typed_payload = fields.Dict(values=fields.Integer())
    inner = fields.Nested(InnerSchema, allow_none=True)


def build_schemas() -> dict[str, Any]:
    spec = APISpec(
        title="test",
        version="v1",
        openapi_version="3.0.2",
        plugins=[MarshmallowPlugin(schema_name_resolver=resolver)],
    )
    spec.components.schema("Outer", schema=OuterSchema)
    return spec.to_dict()["components"]["schemas"]


def test_untyped_dict_documents_additional_properties() -> None:
    # apispec >=6.7.0 documents a `Dict` without a value field as accepting any
    # value instead of omitting `additionalProperties`.
    assert build_schemas()["Outer"]["properties"]["payload"] == {
        "type": "object",
        "additionalProperties": {},
    }


def test_dict_with_values_documents_value_schema() -> None:
    assert build_schemas()["Outer"]["properties"]["typed_payload"] == {
        "type": "object",
        "additionalProperties": {"type": "integer"},
    }


def test_unknown_raise_documents_no_additional_properties() -> None:
    # apispec >=6.8.3 renders marshmallow's default `unknown=RAISE` as
    # `additionalProperties: false`.
    schemas = build_schemas()
    assert schemas["Outer"]["additionalProperties"] is False
    assert schemas["Inner"]["additionalProperties"] is False


def test_nullable_nested_keeps_nullable_branch() -> None:
    # apispec >=6.7.1 renders a nullable `Nested` field as an `anyOf` with a
    # nullable branch; OAS 3.0 ignores `nullable` as a sibling of `$ref`.
    inner = build_schemas()["Outer"]["properties"]["inner"]
    assert "nullable" not in inner
    assert {"$ref": "#/components/schemas/Inner"} in inner["anyOf"]
    assert any(branch.get("nullable") for branch in inner["anyOf"])


def test_published_spec_matches_installed_apispec_rendering() -> None:
    """The committed spec must come from an apispec that renders as above."""
    spec_path = (
        Path(__file__).parents[3] / "docs" / "static" / "resources" / "openapi.json"
    )
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    schemas = spec["components"]["schemas"]

    assert schemas["DashboardRestApi.get_list"]["additionalProperties"] is False
    assert (
        schemas["ChartDataAggregateOptionsSchema"]["properties"]["aggregates"][
            "additionalProperties"
        ]
        == {}
    )
