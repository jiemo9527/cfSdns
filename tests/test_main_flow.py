import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


cloudscraper_module = types.ModuleType("cloudscraper")
setattr(cloudscraper_module, "create_scraper", lambda: None)
sys.modules.setdefault("cloudscraper", cloudscraper_module)

playwright_module = types.ModuleType("playwright")
async_api_module = types.ModuleType("playwright.async_api")
setattr(async_api_module, "async_playwright", lambda: None)
sys.modules.setdefault("playwright", playwright_module)
sys.modules.setdefault("playwright.async_api", async_api_module)

crypto_module = types.ModuleType("Crypto")
cipher_module = types.ModuleType("Crypto.Cipher")
padding_module = types.ModuleType("Crypto.Util.Padding")


class DummyCipher:
    def encrypt(self, data):
        return data

    def decrypt(self, data):
        return data


class DummyDES:
    MODE_CBC = 1
    block_size = 8

    @staticmethod
    def new(*args, **kwargs):
        return DummyCipher()


setattr(cipher_module, "DES", DummyDES)
setattr(padding_module, "pad", lambda data, block_size: data)
setattr(padding_module, "unpad", lambda data, block_size: data)
sys.modules.setdefault("Crypto", crypto_module)
sys.modules.setdefault("Crypto.Cipher", cipher_module)
sys.modules.setdefault("Crypto.Util", types.ModuleType("Crypto.Util"))
sys.modules.setdefault("Crypto.Util.Padding", padding_module)

aliyun_core_module = types.ModuleType("aliyunsdkcore")
aliyun_client_module = types.ModuleType("aliyunsdkcore.client")
setattr(aliyun_client_module, "AcsClient", type("AcsClient", (), {}))
sys.modules.setdefault("aliyunsdkcore", aliyun_core_module)
sys.modules.setdefault("aliyunsdkcore.client", aliyun_client_module)
sys.modules.setdefault("aliyunsdkalidns", types.ModuleType("aliyunsdkalidns"))
sys.modules.setdefault("aliyunsdkalidns.request", types.ModuleType("aliyunsdkalidns.request"))
sys.modules.setdefault("aliyunsdkalidns.request.v20150109", types.ModuleType("aliyunsdkalidns.request.v20150109"))
for module_name, class_name in (
    ("aliyunsdkalidns.request.v20150109.AddDomainRecordRequest", "AddDomainRecordRequest"),
    ("aliyunsdkalidns.request.v20150109.DeleteDomainRecordRequest", "DeleteDomainRecordRequest"),
    ("aliyunsdkalidns.request.v20150109.DescribeDomainRecordsRequest", "DescribeDomainRecordsRequest"),
):
    module = types.ModuleType(module_name)
    setattr(module, class_name, type(class_name, (), {}))
    sys.modules.setdefault(module_name, module)


from src.main import _apply_validation_state, _rotate_aged_production_records
from src.project_config import RuntimeConfig
from src.runtime_state import RuntimeState, get_line_pollution_score, get_record_anomaly_streak, is_record_in_rotation_cooldown
from src.workflow_rules import ValidationSummary


class MainFlowTests(unittest.TestCase):
    def test_apply_validation_state_treats_non_production_ip_as_pollution(self):
        config = RuntimeConfig(domain_rr="www", domain_root="example.com", sleep_time=1800)
        state = RuntimeState()
        summary = ValidationSummary(
            healthy_records={("1.1.1.1", "mobile")},
            anomalous_records={("2.2.2.2", "mobile")},
        )
        production_record_set = {("1.1.1.1", "mobile")}

        deletion_candidates, polluted_lines = _apply_validation_state(config, state, summary, production_record_set)

        self.assertEqual(deletion_candidates, [])
        self.assertEqual(polluted_lines, {"mobile"})
        self.assertEqual(get_line_pollution_score(state, "mobile"), 1)
        self.assertEqual(get_record_anomaly_streak(state, "www", "mobile", "2.2.2.2"), 0)

    def test_rotate_aged_production_records_respects_budgets_and_sets_cooldown(self):
        config = RuntimeConfig(domain_rr="www", domain_root="example.com", sleep_time=1800)
        state = RuntimeState(line_pollution_scores={"mobile": 1, "telecom": 1})
        selected_ips = {
            "mobile": ["3.3.3.3"],
            "unicom": [],
            "telecom": ["5.5.5.5"],
        }
        existing_records = [
            {"RR": "www", "Type": "A", "Line": "mobile", "Value": "1.1.1.1", "CreateTimestamp": 1},
            {"RR": "www", "Type": "A", "Line": "unicom", "Value": "2.2.2.2", "CreateTimestamp": 1},
            {"RR": "www", "Type": "A", "Line": "telecom", "Value": "6.6.6.6", "CreateTimestamp": 1},
        ]
        after_mobile_records = [
            {"RR": "www", "Type": "A", "Line": "mobile", "Value": "1.1.1.1", "CreateTimestamp": 1},
            {"RR": "www", "Type": "A", "Line": "mobile", "Value": "3.3.3.3", "CreateTimestamp": 2},
            {"RR": "www", "Type": "A", "Line": "unicom", "Value": "2.2.2.2", "CreateTimestamp": 1},
            {"RR": "www", "Type": "A", "Line": "telecom", "Value": "6.6.6.6", "CreateTimestamp": 1},
        ]
        after_telecom_records = [
            {"RR": "www", "Type": "A", "Line": "mobile", "Value": "1.1.1.1", "CreateTimestamp": 1},
            {"RR": "www", "Type": "A", "Line": "mobile", "Value": "3.3.3.3", "CreateTimestamp": 2},
            {"RR": "www", "Type": "A", "Line": "unicom", "Value": "2.2.2.2", "CreateTimestamp": 1},
            {"RR": "www", "Type": "A", "Line": "telecom", "Value": "6.6.6.6", "CreateTimestamp": 1},
            {"RR": "www", "Type": "A", "Line": "telecom", "Value": "5.5.5.5", "CreateTimestamp": 2},
        ]

        fake_now = 2_000_000_000
        with patch("src.main.time.time", return_value=fake_now), \
             patch("src.runtime_state.time.time", return_value=fake_now), \
             patch("src.main._get_current_production_records", side_effect=[existing_records, after_mobile_records, after_telecom_records]), \
             patch("src.main.cf2alidns.add_record") as add_record_mock, \
             patch("src.main.cf2alidns.delete_record_by_value") as delete_record_mock:
            _rotate_aged_production_records(
                config,
                state,
                selected_ips_by_carrier=selected_ips,
                deleted_records=[],
                polluted_lines={"mobile", "telecom"},
            )

        self.assertEqual(add_record_mock.call_count, 2)
        self.assertEqual(delete_record_mock.call_count, 2)
        with patch("src.runtime_state.time.time", return_value=fake_now):
            self.assertTrue(is_record_in_rotation_cooldown(state, "www", "mobile", "1.1.1.1"))
            self.assertTrue(is_record_in_rotation_cooldown(state, "www", "telecom", "6.6.6.6"))


if __name__ == "__main__":
    unittest.main()
