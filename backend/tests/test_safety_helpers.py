import json
import sys
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
TEST_TMP_ROOT = BACKEND_DIR / "tests" / "tmp"
sys.path.insert(0, str(BACKEND_DIR))

from file_store import atomic_write_bytes, atomic_write_text, safe_child_path
from llm_client import build_ai_http_headers, format_llm_error
from model_routes import load_model_routes, public_model_routes, save_model_routes
from routers.chat import _chunk_delta_content, _is_model_status_question, _resolve_chat_model
from upload_validation import (
    UploadValidationError,
    validate_excel_upload,
    validate_image_upload,
    validate_pdf_upload,
)


class UploadValidationTests(unittest.TestCase):
    def test_pdf_upload_uses_safe_basename_and_checks_magic(self):
        safe_name = validate_pdf_upload(r"..\approval.pdf", "application/pdf", b"%PDF-1.7\n")

        self.assertEqual(safe_name, "approval.pdf")

        with self.assertRaises(UploadValidationError):
            validate_pdf_upload("approval.pdf", "application/pdf", b"not a pdf")

    def test_image_upload_rejects_bad_extension_even_with_image_content_type(self):
        with self.assertRaises(UploadValidationError):
            validate_image_upload("signin.exe", "image/png", b"\x89PNG\r\n\x1a\n")

    def test_excel_upload_rejects_content_type_mismatch(self):
        with self.assertRaises(UploadValidationError):
            validate_excel_upload(
                "ledger.xlsx",
                "text/plain",
                b"PK\x03\x04fake workbook",
            )


class FileStoreTests(unittest.TestCase):
    def test_atomic_writes_create_parent_and_replace_file(self):
        TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=TEST_TMP_ROOT) as tmpdir:
            target = Path(tmpdir) / "nested" / "data.json"

            atomic_write_text(target, json.dumps({"v": 1}), encoding="utf-8")
            atomic_write_text(target, json.dumps({"v": 2}), encoding="utf-8")

            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {"v": 2})
            self.assertFalse(list(target.parent.glob("*.tmp")))

    def test_atomic_write_bytes_replaces_existing_file(self):
        TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=TEST_TMP_ROOT) as tmpdir:
            target = Path(tmpdir) / "out.bin"
            target.write_bytes(b"old")

            atomic_write_bytes(target, b"new")

            self.assertEqual(target.read_bytes(), b"new")

    def test_safe_child_path_rejects_path_traversal(self):
        TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=TEST_TMP_ROOT) as tmpdir:
            base = Path(tmpdir)

            self.assertEqual(safe_child_path(base, "sess_abc.json").parent, base.resolve())
            with self.assertRaises(ValueError):
                safe_child_path(base, "..", "escape.json")


class LlmClientTests(unittest.TestCase):
    def test_stream_chunk_without_choices_is_ignored(self):
        self.assertIsNone(_chunk_delta_content(SimpleNamespace(choices=[])))

    def test_stream_chunk_extracts_delta_content(self):
        chunk = SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(content="你好"))]
        )

        self.assertEqual(_chunk_delta_content(chunk), "你好")

    def test_requested_chat_model_must_be_allowed(self):
        allowed = ["qwen2.5-72b", "DeepSeek-V3", "glm-5-outside"]

        self.assertEqual(_resolve_chat_model("DeepSeek-V3", allowed, "qwen2.5-72b"), "DeepSeek-V3")
        self.assertEqual(_resolve_chat_model("unknown-model", allowed, "qwen2.5-72b"), "qwen2.5-72b")

    def test_model_resolution_falls_back_to_first_allowed_when_default_is_missing(self):
        self.assertEqual(_resolve_chat_model("", ["DeepSeek-V3"], "qwen2.5-72b"), "DeepSeek-V3")

    def test_model_status_question_is_detected(self):
        self.assertTrue(_is_model_status_question("你是什么模型"))
        self.assertTrue(_is_model_status_question("当前模型是什么？"))
        self.assertFalse(_is_model_status_question("请帮我起草授权请示"))

    def test_runtime_model_routes_can_be_loaded_from_json(self):
        TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=TEST_TMP_ROOT) as tmpdir:
            path = Path(tmpdir) / "model_routes.json"
            path.write_text(json.dumps({
                "default_chat_model": "DeepSeek-V3",
                "default_vision_model": "qwen2.5-vl-72b",
                "chat_models": ["qwen2.5-72b", "DeepSeek-V3"],
                "vision_models": ["qwen2.5-vl-72b"],
            }), encoding="utf-8")

            routes = load_model_routes(path)

            self.assertEqual(routes["default_chat_model"], "DeepSeek-V3")
            self.assertEqual(routes["chat_models"], ["qwen2.5-72b", "DeepSeek-V3"])

    def test_runtime_model_routes_public_shape_has_labels(self):
        TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=TEST_TMP_ROOT) as tmpdir:
            path = Path(tmpdir) / "model_routes.json"
            save_model_routes({
                "default_chat_model": "DeepSeek-V3",
                "chat_models": ["DeepSeek-V3"],
                "vision_models": ["qwen2.5-vl-72b"],
            }, path)

            routes = public_model_routes(path)

            self.assertEqual(routes["default_chat_model"], "DeepSeek-V3")
            self.assertEqual(routes["chat_models"][0]["value"], "DeepSeek-V3")
            self.assertEqual(routes["chat_models"][0]["label"], "DeepSeek V3")

    def test_host_header_is_optional(self):
        self.assertEqual(build_ai_http_headers("aiplus.airchina.com.cn:18080"), {"Host": "aiplus.airchina.com.cn:18080"})
        self.assertEqual(build_ai_http_headers(""), {})

    def test_certificate_verify_failure_gets_actionable_message(self):
        message = format_llm_error(
            Exception(
                "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: "
                "IP address mismatch, certificate is not valid for '10.150.224.182'"
            )
        )

        self.assertIn("AI 服务连接失败", message)
        self.assertIn("证书校验失败", message)
        self.assertIn("AI_HTTP_VERIFY_SSL=false", message)


if __name__ == "__main__":
    unittest.main()
