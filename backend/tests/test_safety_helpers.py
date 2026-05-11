import json
import sys
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import MagicMock, patch

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

    def test_audit_review_model_uses_deepseek_not_global_default(self):
        from routers.audit import _call_review_llm

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "[]"
        mock_client.chat.completions.create.return_value = mock_response

        with patch("routers.audit.get_llm_client", return_value=mock_client):
            _call_review_llm([{
                "seq": 1,
                "issue": "issue",
                "description": "",
                "category_l1": "其他",
                "category_l2": "其他",
                "domain": "工程领域",
            }], ["工程领域"])

        self.assertEqual(mock_client.chat.completions.create.call_args.kwargs["model"], "DeepSeek-V3")

    def test_audit_cross_check_models_are_fixed_without_removing_glm_globally(self):
        from routers.audit import AUDIT_CLASSIFY_MODEL, AUDIT_REVIEW_MODEL
        from model_routes import load_model_routes

        TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=TEST_TMP_ROOT) as tmpdir:
            path = Path(tmpdir) / "model_routes.json"
            path.write_text(json.dumps({
                "default_chat_model": "glm-5-outside",
                "chat_models": ["qwen2.5-72b", "DeepSeek-V3", "glm-5-outside"],
                "vision_models": ["qwen2.5-vl-72b"],
            }), encoding="utf-8")

            routes = load_model_routes(path)

        self.assertEqual(AUDIT_CLASSIFY_MODEL, "qwen2.5-72b")
        self.assertEqual(AUDIT_REVIEW_MODEL, "DeepSeek-V3")
        self.assertIn("glm-5-outside", routes["chat_models"])


class OllamaModelRoutingTests(unittest.TestCase):
    """视觉客户端路由：Ollama 本地模型 vs 云端 AI 平台"""

    def _make_mock_client(self):
        return MagicMock()

    def test_routes_to_ollama_when_url_configured(self):
        """qwen3-vl:8b + OLLAMA_BASE_URL 已设置 → 使用 Ollama 客户端"""
        import utils.image_analyzer as ia
        mock_ollama = self._make_mock_client()
        mock_regular = self._make_mock_client()
        with patch.object(ia, 'OLLAMA_BASE_URL', 'http://192.168.9.226:11434/v1'), \
             patch.object(ia, 'get_ollama_client', return_value=mock_ollama) as spy_ollama, \
             patch.object(ia, 'get_client', return_value=mock_regular) as spy_regular:
            ia.get_vision_client('qwen3-vl:8b')
            spy_ollama.assert_called_once()
            spy_regular.assert_not_called()

    def test_falls_back_to_cloud_for_non_ollama_model(self):
        """云端模型（qwen2.5-vl-72b）始终走 AI 平台客户端"""
        import utils.image_analyzer as ia
        mock_client = self._make_mock_client()
        with patch.object(ia, 'get_ollama_client', return_value=mock_client) as spy_ollama, \
             patch.object(ia, 'get_client', return_value=mock_client) as spy_regular:
            ia.get_vision_client('qwen2.5-vl-72b')
            spy_regular.assert_called_once()
            spy_ollama.assert_not_called()

    def test_falls_back_to_cloud_when_ollama_url_empty(self):
        """qwen3-vl:8b 但 OLLAMA_BASE_URL 为空 → 回退到 AI 平台客户端"""
        import utils.image_analyzer as ia
        mock_client = self._make_mock_client()
        with patch.object(ia, 'OLLAMA_BASE_URL', ''), \
             patch.object(ia, 'get_ollama_client', return_value=mock_client) as spy_ollama, \
             patch.object(ia, 'get_client', return_value=mock_client) as spy_regular:
            ia.get_vision_client('qwen3-vl:8b')
            spy_regular.assert_called_once()
            spy_ollama.assert_not_called()


class OllamaModelLabelTests(unittest.TestCase):
    """Ollama 模型在运行时路由中的标签与加载"""

    def test_ollama_model_label_in_public_routes(self):
        """public_model_routes 返回 qwen3-vl:8b 的中文标签"""
        TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=TEST_TMP_ROOT) as tmpdir:
            path = Path(tmpdir) / "model_routes.json"
            save_model_routes({
                "vision_models": ["qwen2.5-vl-72b", "qwen3-vl:8b"],
            }, path)
            routes = public_model_routes(path)
            labels = {m["value"]: m["label"] for m in routes["vision_models"]}
            self.assertEqual(labels.get("qwen3-vl:8b"), "Qwen3 VL 8B (本地)")

    def test_ollama_model_preserved_after_load(self):
        """model_routes.json 中包含 qwen3-vl:8b 时正确加载，不丢失"""
        TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=TEST_TMP_ROOT) as tmpdir:
            path = Path(tmpdir) / "model_routes.json"
            path.write_text(json.dumps({
                "vision_models": ["qwen2.5-vl-72b", "qwen3-vl:8b"],
            }), encoding="utf-8")
            routes = load_model_routes(path)
            self.assertIn("qwen3-vl:8b", routes["vision_models"])

    def test_ollama_model_is_valid_default_vision_model(self):
        """可以将 qwen3-vl:8b 设为默认视觉模型"""
        TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=TEST_TMP_ROOT) as tmpdir:
            path = Path(tmpdir) / "model_routes.json"
            save_model_routes({
                "default_vision_model": "qwen3-vl:8b",
                "vision_models": ["qwen2.5-vl-72b", "qwen3-vl:8b"],
            }, path)
            routes = load_model_routes(path)
            self.assertEqual(routes["default_vision_model"], "qwen3-vl:8b")


class SignInParseTests(unittest.TestCase):
    """parse_sign_in_result：AI 返回文本解析"""

    def setUp(self):
        from utils.image_analyzer import parse_sign_in_result
        self.parse = parse_sign_in_result

    def test_parses_full_result(self):
        text = "主题：安全培训\n地点：会议室A\n时间：2026-05-08\n人数：23"
        result = self.parse(text)
        self.assertEqual(result["topic"], "安全培训")
        self.assertEqual(result["location"], "会议室A")
        self.assertEqual(result["date"], "2026-05-08")
        self.assertEqual(result["count"], 23)

    def test_count_extracts_digits_only(self):
        """人数字段含多余文字时只取数字"""
        result = self.parse("人数：共 12 人")
        self.assertEqual(result["count"], 12)

    def test_missing_fields_default_to_empty(self):
        """缺失字段返回默认空值，不报错"""
        result = self.parse("人数：5")
        self.assertEqual(result["topic"], "")
        self.assertEqual(result["count"], 5)

    def test_invalid_count_defaults_to_zero(self):
        """人数无法解析时返回 0"""
        result = self.parse("人数：不详")
        self.assertEqual(result["count"], 0)


if __name__ == "__main__":
    unittest.main()
