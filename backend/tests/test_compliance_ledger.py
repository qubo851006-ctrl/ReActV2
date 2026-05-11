import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import openpyxl

BACKEND_DIR = Path(__file__).resolve().parents[1]
TEST_TMP_ROOT = BACKEND_DIR / "tests" / "tmp"
sys.path.insert(0, str(BACKEND_DIR))

from utils.compliance_ledger import (  # noqa: E402
    append_record,
    build_review_rows,
    create_compliance_workbook,
    extract_compliance_item,
    load_responsible_persons,
    normalize_review_opinion,
    save_responsible_persons,
)


class _FakeMessage:
    def __init__(self, content: str):
        self.content = content


class _FakeChoice:
    def __init__(self, content: str):
        self.message = _FakeMessage(content)


class _FakeResponse:
    def __init__(self, content: str):
        self.choices = [_FakeChoice(content)]


class _FakeCompletions:
    def __init__(self, responses: list[str]):
        self.responses = list(responses)
        self.models: list[str] = []

    def create(self, **kwargs):
        self.models.append(kwargs["model"])
        return _FakeResponse(self.responses.pop(0))


class _FakeChat:
    def __init__(self, completions: _FakeCompletions):
        self.completions = completions


class _FakeClient:
    def __init__(self, completions: _FakeCompletions):
        self.chat = _FakeChat(completions)


class ComplianceLedgerOpinionTests(unittest.TestCase):
    def test_normalize_review_opinion_prefers_disagreement(self):
        self.assertEqual(normalize_review_opinion("不同意该方案，建议重新论证"), "不予同意")

    def test_normalize_review_opinion_detects_supplement_suggestion(self):
        self.assertEqual(normalize_review_opinion("拟同意，建议补充预算测算依据"), "建议补充完善")

    def test_normalize_review_opinion_defaults_to_agree(self):
        self.assertEqual(normalize_review_opinion("拟同意。"), "同意")


class ComplianceLedgerRowsTests(unittest.TestCase):
    def test_build_review_rows_expands_multiple_countersign_departments(self):
        item = {
            "undertaking": {
                "department": "财务部",
                "person": "杨焕",
                "time": "2026-05-01",
                "opinion_text": "拟同意。",
            },
            "countersign": [
                {
                    "department": "人力资源部",
                    "person": "陈锐",
                    "time": "2026-05-02",
                    "opinion_text": "建议补充人员安排。",
                    "detail": "建议补充人员安排。",
                    "implementation": "已按要求补充完善",
                },
                {
                    "department": "财务部",
                    "person": "杨焕",
                    "time": "2026-05-03",
                    "opinion_text": "同意。",
                },
            ],
            "compliance": {
                "department": "审计部/法务合规部",
                "person": "李莹",
                "time": "2026-05-04",
                "opinion_text": "拟同意。",
            },
            "chief": {
                "person": "胡鹏斌",
                "time": "2026-05-05",
                "opinion_text": "拟同意。",
            },
        }

        rows = build_review_rows(item)

        self.assertEqual([row["review_unit"] for row in rows], [
            "首席合规官",
            "合规管理牵头部门（审计部/法务合规部）",
            "会签单位（人力资源部）",
            "会签单位（财务部）",
            "承办单位（财务部）",
        ])
        self.assertEqual(rows[2]["review_opinion"], "建议补充完善")
        self.assertEqual(rows[2]["detail"], "建议补充人员安排。")
        self.assertEqual(rows[2]["implementation"], "已按要求补充完善")


class ComplianceLedgerWorkbookTests(unittest.TestCase):
    def test_create_workbook_merges_matter_columns_and_expands_review_rows(self):
        TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=TEST_TMP_ROOT) as tmpdir:
            output = Path(tmpdir) / "ledger.xlsx"
            records = [{
                "sequence": 1,
                "title": "关于计划外新增企业知识库建设项目（一期）及立项的请示",
                "procedure": "总办会审议",
                "undertaking_department": "法务合规部",
                "background_materials": ["项目立项报告", "预算测算表"],
                "review_rows": [
                    {
                        "review_time": "2026-05-05",
                        "review_unit": "首席合规官",
                        "review_opinion": "同意",
                        "detail": "/",
                        "implementation": "/",
                    },
                    {
                        "review_time": "2026-05-04",
                        "review_unit": "合规管理牵头部门（审计部/法务合规部）",
                        "review_opinion": "建议补充完善",
                        "detail": "建议补充预算测算依据",
                        "implementation": "已按要求补充完善",
                    },
                    {
                        "review_time": "2026-05-03",
                        "review_unit": "会签单位（财务部）",
                        "review_opinion": "同意",
                        "detail": "/",
                        "implementation": "/",
                    },
                    {
                        "review_time": "2026-05-01",
                        "review_unit": "承办单位（财务部）",
                        "review_opinion": "同意",
                        "detail": "/",
                        "implementation": "/",
                    },
                ],
            }]

            create_compliance_workbook(records, output)
            wb = openpyxl.load_workbook(output)
            ws = wb["合规管理牵头部门合规审查台账"]

            self.assertEqual(ws["A1"].value, "合规管理牵头部门合规审查工作台账")
            self.assertEqual(ws["A2"].value, "序号")
            self.assertEqual(ws["A3"].value, 1)
            self.assertEqual(ws["B3"].value, records[0]["title"])
            self.assertEqual(ws["C3"].value, "总办会审议")
            self.assertEqual(ws["E4"].value, "合规管理牵头部门（审计部/法务合规部）")
            self.assertEqual(ws["F4"].value, "建议补充完善")
            self.assertEqual(ws["J3"].value, "项目立项报告、预算测算表")
            self.assertIn("A3:A6", [str(rng) for rng in ws.merged_cells.ranges])
            self.assertIn("B3:B6", [str(rng) for rng in ws.merged_cells.ranges])


class ComplianceLedgerPersistenceTests(unittest.TestCase):
    def test_responsible_persons_config_can_be_saved_and_reloaded(self):
        TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=TEST_TMP_ROOT) as tmpdir:
            path = Path(tmpdir) / "responsible_persons.json"

            saved = save_responsible_persons({"财务部": "杨焕", " 空部门 ": " "}, path)
            loaded = load_responsible_persons(path)

            self.assertEqual(saved, {"财务部": "杨焕"})
            self.assertEqual(loaded["财务部"], "杨焕")
            self.assertNotIn(" 空部门 ", loaded)

    def test_append_record_assigns_natural_sequence_numbers(self):
        TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=TEST_TMP_ROOT) as tmpdir:
            path = Path(tmpdir) / "records.json"
            base_record = {
                "title": "事项",
                "procedure": "董事会审议",
                "undertaking_department": "法务合规部",
                "background_materials": [],
                "review_rows": [],
            }

            records = append_record(base_record, path)
            records = append_record({**base_record, "title": "事项二"}, path)

            self.assertEqual([r["sequence"] for r in records], [1, 2])
            self.assertEqual(records[1]["title"], "事项二")


class ComplianceLedgerModelTests(unittest.TestCase):
    def test_extract_compliance_item_uses_qwen_then_deepseek_review(self):
        qwen_json = """
        {
          "title": "原始标题",
          "procedure": "董事会审议",
          "attachments": ["附件一.pdf"],
          "undertaking": {"department": "财务部", "person": "杨焕", "time": "2026-05-01", "opinion_text": "拟同意", "detail": "", "implementation": "/"},
          "countersign": [],
          "compliance": {"department": "审计部/法务合规部", "person": "李莹", "time": "2026-05-02", "opinion_text": "拟同意", "detail": "", "implementation": "/"},
          "chief": {"person": "胡鹏斌", "time": "2026-05-03", "opinion_text": "拟同意", "detail": "", "implementation": "/"},
          "warnings": []
        }
        """
        deepseek_json = """
        {
          "title": "校验后的标题",
          "procedure": "总办会审议",
          "attachments": ["附件二.xlsx"],
          "undertaking": {"department": "财务部", "person": "杨焕", "time": "2026-05-01", "opinion_text": "拟同意", "detail": "", "implementation": "/"},
          "countersign": [],
          "compliance": {"department": "审计部/法务合规部", "person": "李莹", "time": "2026-05-02", "opinion_text": "拟同意", "detail": "", "implementation": "/"},
          "chief": {"person": "胡鹏斌", "time": "2026-05-03", "opinion_text": "拟同意", "detail": "", "implementation": "/"},
          "warnings": ["DeepSeek 已校验"]
        }
        """
        completions = _FakeCompletions([qwen_json, deepseek_json])

        with patch("llm_client.get_llm_client", return_value=_FakeClient(completions)):
            item = extract_compliance_item("OA正文内容", {"财务部": "杨焕"})

        self.assertEqual(completions.models, ["qwen2.5-72b", "DeepSeek-V3"])
        self.assertNotIn("glm-5-outside", completions.models)
        self.assertEqual(item["title"], "校验后的标题")
        self.assertEqual(item["procedure"], "总办会审议")
        self.assertEqual(item["background_materials"], ["附件二"])
        self.assertIn("DeepSeek 已校验", item["warnings"])


if __name__ == "__main__":
    unittest.main()
