"""验证供应商和能力分发，以及提交、状态查询和交付记录之间的衔接。"""

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from commands import submit, status, deliver
from core import submission_store as store
from core.catalogs import CATALOGS
from core.http import ProviderError
from providers import get_capability, get_provider, compile_request, calculate_asset_inputs
from config_fixture import config_fixture
from test_document_contract import image
from test_native_video import request as video_request
from test_native_reference_video import request as reference_request, metadata
from test_native_volcengine_layers import png, outputs

OPERATIONS = (
    "text-to-image",
    "image-to-image",
    "decompose-layers",
    "text-to-video",
    "image-to-video",
    "reference-to-video",
    "extend-video",
)


def prepare(directory, provider, operation):
    directory.mkdir()
    if operation in OPERATIONS[:3]:
        spec = image()
        spec.update(provider=provider, operation=operation)
        spec["payload"]["model"] = CATALOGS[provider]["models"]["seedream-5.0-flash"]["id"]
        spec["payload"]["layer_decomposition"] = operation == "decompose-layers"
        if operation != "text-to-image":
            source = directory / "source.png"
            source.write_bytes(png())
            spec["assets"] = [
                {"id": "source", "kind": "image", "source": str(source), "purpose": "参考图"}
            ]
        parameters = {"size": spec["payload"]["size"]}
    elif operation in ("text-to-video", "image-to-video"):
        spec = video_request(
            provider=provider, mode="first-frame" if operation == "image-to-video" else None
        )
        parameters = {key: spec["payload"][key] for key in ("resolution", "ratio", "duration")}
    else:
        spec = reference_request(
            provider=provider,
            operation=operation,
            mode="after" if operation == "extend-video" else "reference",
        )
        parameters = {key: spec["payload"][key] for key in ("resolution", "ratio", "duration")}
    inputs = {
        "provider": provider,
        "operation": operation,
        "model": spec["payload"]["model"],
        **parameters,
        "assets": [
            {key: a[key] for key in ("id", "kind", "source")} for a in spec.get("assets", [])
        ],
    }
    if "mode" in spec:
        inputs["mode"] = spec["mode"]
    measurements = [{**asset, "metadata": metadata(asset["kind"])} for asset in inputs["assets"]]
    with patch("core.media_probe.probe_asset", side_effect=measurements):
        quote = calculate_asset_inputs(inputs)
    # 本地素材必须绑定真实文件哈希，不能使用虚构的测量记录。
    if operation in ("image-to-image", "decompose-layers"):
        quote = calculate_asset_inputs(inputs)
    compiled = compile_request(spec, quote["calculation"]["assets"])
    selected = {
        "model": spec["payload"]["model"],
        "operation": operation,
        "parameters": compiled["parameters"],
        "assets": [{"id": a["id"]} for a in spec.get("assets", [])],
    }
    if "mode" in spec:
        selected["mode"] = spec["mode"]
    store.write(directory / (provider + "-priceing.json"), quote)
    store.write(
        directory / "request.json",
        {
            "original_prompt": spec["original_prompt"],
            "optimized_prompt": compiled["prompt"],
            "intent": {"operation": operation},
            "assets": spec.get("assets", []),
            "providers": {provider: selected},
        },
    )
    return spec


class CapabilityLifecycle(unittest.TestCase):
    def test_all_four_stages_route_to_the_saved_supplier_and_capability(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for provider in ("volcengine", "byteplus"):
                client = get_provider(provider)["adapter"]
                other = get_provider("byteplus" if provider == "volcengine" else "volcengine")[
                    "adapter"
                ]
                for operation in OPERATIONS:
                    with self.subTest(provider=provider, operation=operation):
                        work = root / (provider + "-" + operation)
                        spec = prepare(work, provider, operation)
                        capability = get_capability(provider, operation)
                        is_image = operation in OPERATIONS[:3]
                        task_id = provider + "-" + operation
                        response = (
                            {"data": outputs()}
                            if operation == "decompose-layers"
                            else (
                                {"data": [{"url": "https://example.com/result.png"}]}
                                if is_image
                                else {"id": task_id}
                            )
                        )
                        with config_fixture({client.KEY_ENV: "fixture-only"}), patch.object(
                            client, "request", return_value=response
                        ) as post, patch.object(other, "request") as wrong_post, patch.object(
                            capability, "submit", wraps=capability.submit
                        ) as routed, patch.object(
                            capability,
                            "calculate_cost",
                            side_effect=AssertionError("Submission must reuse the saved quote"),
                        ):
                            state = submit.submit(
                                work, spec, "TEST CONFIRMATION", accept_uncertain=True
                            )
                        routed.assert_called_once()
                        post.assert_called_once()
                        wrong_post.assert_not_called()
                        original = copy.deepcopy(store.read(state["submission"])["response"])
                        success = {
                            "id": task_id,
                            "status": "succeeded",
                            "content": {"video_url": "https://example.com/result.mp4"},
                        }

                        def save(url, path):
                            path.write_bytes(png() if is_image else b"fixture-video")

                        destination = root / ("delivery-" + task_id)
                        destination.mkdir()
                        with patch.object(
                            client, "status", return_value=success
                        ) as query, patch.object(other, "status") as wrong_query, patch.object(
                            capability, "status", wraps=capability.status
                        ) as routed_status, patch.object(
                            capability, "deliver", wraps=capability.deliver
                        ) as routed_delivery, patch(
                            "core.download.download_url", side_effect=save
                        ) as get, patch(
                            "core.media_validate.video_metadata",
                            return_value={
                                "width": 854,
                                "height": 480,
                                "duration": 4,
                                "has_audio": False,
                            },
                        ):
                            self.assertTrue(
                                status.status_result(status.status(state["submission"]))["success"]
                            )
                            first = deliver.deliver(state["submission"], destination)
                            second = deliver.deliver(state["submission"], destination)
                        self.assertGreater(routed_status.call_count, 0)
                        self.assertEqual(routed_delivery.call_count, 1)
                        wrong_query.assert_not_called()
                        self.assertEqual(query.call_count == 0, is_image)
                        self.assertEqual(
                            get.call_count, 2 if operation == "decompose-layers" else 1
                        )
                        self.assertEqual(first["files"], second["files"])
                        record = store.read(state["submission"])
                        self.assertEqual(record["response"], original)
                        self.assertTrue(record["execution"]["delivery_complete"])
                        self.assertEqual(record["execution"]["compiled"]["operation"], operation)
                        if operation == "decompose-layers":
                            self.assertTrue(Path(first["metadata"]["path"]).is_file())

    def test_unknown_post_never_reposts_when_querying_or_delivering(self):
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp) / "task"
            spec = prepare(work, "volcengine", "text-to-video")
            client = get_provider("volcengine")["adapter"]
            with config_fixture({client.KEY_ENV: "fixture-only"}), patch.object(
                client, "request", side_effect=ProviderError("timeout", uncertain=True)
            ) as post:
                with self.assertRaises(ProviderError):
                    submit.submit(work, spec, "TEST CONFIRMATION")
                submission = work / "submit-001.json"
                self.assertFalse(status.status_result(status.status(submission))["success"])
                with self.assertRaises(ValueError):
                    deliver.deliver(submission, Path(temp))
                with self.assertRaisesRegex(ValueError, "outcome unknown"):
                    submit.submit(work, spec, "TEST CONFIRMATION")
            post.assert_called_once()
            self.assertEqual(store.read(submission)["execution"]["state"], "submission_unknown")

    def test_query_rejects_another_task_id_and_preserves_post_response(self):
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp) / "task"
            spec = prepare(work, "byteplus", "text-to-video")
            client = get_provider("byteplus")["adapter"]
            with config_fixture({client.KEY_ENV: "fixture-only"}), patch.object(
                client, "request", return_value={"id": "original"}
            ):
                state = submit.submit(work, spec, "TEST CONFIRMATION")
            with patch.object(
                client, "status", return_value={"id": "different", "status": "succeeded"}
            ):
                with self.assertRaisesRegex(ValueError, "different task ID"):
                    status.status(state["submission"])
            record = store.read(state["submission"])
            self.assertEqual(record["response"], {"id": "original"})
            self.assertEqual(record["execution"]["state"], "queued")

    def test_conflicting_saved_supplier_cannot_route_to_another_account(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "submit-001.json"
            store.write(
                path,
                {
                    "provider": "byteplus",
                    "operation": "text-to-video",
                    "execution": {
                        "state": "queued",
                        "task_id": "original",
                        "compiled": {
                            "provider": "volcengine",
                            "operation": "text-to-video",
                            "kind": "video",
                        },
                    },
                },
            )
            with patch.object(
                get_provider("byteplus")["adapter"], "status"
            ) as overseas, patch.object(
                get_provider("volcengine")["adapter"], "status"
            ) as domestic:
                with self.assertRaisesRegex(ValueError, "differs from compiled plan"):
                    status.status(path)
            overseas.assert_not_called()
            domestic.assert_not_called()
