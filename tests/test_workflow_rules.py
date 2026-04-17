import json
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.workflow_rules import (
    collect_bad_records,
    filter_and_select_ips,
    should_freeze_production_deletions,
    summarize_validation_results,
)


class FilterAndSelectIpsTests(unittest.TestCase):
    def test_filter_and_select_ips_keeps_only_fast_530_results(self):
        raw_results = [
            {"检测点": "移动上海", "状态": "530", "总耗时": "0.30s", "响应IP": "1.1.1.1"},
            {"检测点": "联通北京", "状态": "530", "总耗时": "0.99s", "响应IP": "2.2.2.2"},
            {"检测点": "电信广州", "状态": "530", "总耗时": "0.50s", "响应IP": "3.3.3.3"},
            {"检测点": "移动深圳", "状态": "200", "总耗时": "0.10s", "响应IP": "4.4.4.4"},
            {"检测点": "联通杭州", "状态": "530", "总耗时": "1.10s", "响应IP": "5.5.5.5"},
            {"检测点": "电信南京", "状态": "530", "总耗时": "0.20s", "响应IP": "解析失败"},
            {"检测点": "移动成都", "状态": "530", "总耗时": "abc", "响应IP": "6.6.6.6"},
        ]

        result = filter_and_select_ips(json.dumps(raw_results, ensure_ascii=False))

        self.assertEqual(
            result,
            {
                "mobile": ["1.1.1.1"],
                "unicom": ["2.2.2.2"],
                "telecom": ["3.3.3.3"],
            },
        )

    def test_filter_and_select_ips_deduplicates_same_ip(self):
        raw_results = [
            {"检测点": "移动上海", "状态": "530", "总耗时": "0.30s", "响应IP": "1.1.1.1"},
            {"检测点": "移动北京", "状态": "530", "总耗时": "0.40s", "响应IP": "1.1.1.1"},
        ]

        result = filter_and_select_ips(json.dumps(raw_results, ensure_ascii=False))

        self.assertEqual(result["mobile"], ["1.1.1.1"])


class CollectBadRecordsTests(unittest.TestCase):
    def test_collect_bad_records_marks_failure_and_slow_records(self):
        raw_results = [
            {"检测点": "移动上海", "状态": "失败", "总耗时": "0.20s", "响应IP": "1.1.1.1"},
            {"检测点": "联通北京", "状态": "530", "总耗时": "2.00s", "响应IP": "2.2.2.2"},
            {"检测点": "电信广州", "状态": "530", "总耗时": "1.99s", "响应IP": "3.3.3.3"},
        ]

        result = collect_bad_records(json.dumps(raw_results, ensure_ascii=False))
        normalized = sorted((item["ip"], item["line"]) for item in result)

        self.assertEqual(normalized, [("1.1.1.1", "mobile"), ("2.2.2.2", "unicom")])

    def test_collect_bad_records_deduplicates_and_truncates(self):
        raw_results = [
            {"检测点": "移动节点", "状态": "失败", "总耗时": "0.20s", "响应IP": f"1.1.1.{index}"}
            for index in range(1, 13)
        ]
        raw_results.append({"检测点": "移动重复", "状态": "失败", "总耗时": "0.30s", "响应IP": "1.1.1.1"})

        result = collect_bad_records(json.dumps(raw_results, ensure_ascii=False))
        normalized = [(item["ip"], item["line"]) for item in result]

        self.assertEqual(len(normalized), 5)
        self.assertEqual(len(set(normalized)), 5)
        self.assertTrue(all(line == "mobile" for _, line in normalized))


class ValidationSummaryTests(unittest.TestCase):
    def test_summarize_validation_results_marks_record_healthy_if_any_point_is_healthy(self):
        raw_results = [
            {"检测点": "移动上海", "状态": "失败", "总耗时": "2.5s", "响应IP": "1.1.1.1"},
            {"检测点": "移动北京", "状态": "530", "总耗时": "0.40s", "响应IP": "1.1.1.1"},
        ]

        summary = summarize_validation_results(json.dumps(raw_results, ensure_ascii=False))

        self.assertIsNotNone(summary)
        assert summary is not None
        self.assertIn(("1.1.1.1", "mobile"), summary.healthy_records)
        self.assertNotIn(("1.1.1.1", "mobile"), summary.anomalous_records)

    def test_should_freeze_production_deletions_when_all_lines_are_anomalous(self):
        raw_results = [
            {"检测点": "移动上海", "状态": "失败", "总耗时": "2.5s", "响应IP": "1.1.1.1"},
            {"检测点": "联通北京", "状态": "失败", "总耗时": "2.5s", "响应IP": "2.2.2.2"},
            {"检测点": "电信广州", "状态": "失败", "总耗时": "2.5s", "响应IP": "3.3.3.3"},
        ]

        summary = summarize_validation_results(json.dumps(raw_results, ensure_ascii=False))

        self.assertTrue(should_freeze_production_deletions(summary))

    def test_should_not_freeze_when_still_has_healthy_points(self):
        raw_results = [
            {"检测点": "移动上海", "状态": "失败", "总耗时": "2.5s", "响应IP": "1.1.1.1"},
            {"检测点": "联通北京", "状态": "530", "总耗时": "0.30s", "响应IP": "2.2.2.2"},
        ]

        summary = summarize_validation_results(json.dumps(raw_results, ensure_ascii=False))

        self.assertFalse(should_freeze_production_deletions(summary))

    def test_parse_failure_counts_as_unresolved_anomaly_for_freeze(self):
        raw_results = [
            {"检测点": "移动上海", "状态": "失败", "总耗时": "--", "响应IP": "解析失败"},
            {"检测点": "联通北京", "状态": "失败", "总耗时": "--", "响应IP": ""},
        ]

        summary = summarize_validation_results(json.dumps(raw_results, ensure_ascii=False))

        self.assertIsNotNone(summary)
        assert summary is not None
        self.assertEqual(summary.unresolved_anomaly_points, 2)
        self.assertTrue(should_freeze_production_deletions(summary))


if __name__ == "__main__":
    unittest.main()
