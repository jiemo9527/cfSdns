import importlib
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


class DummyDescribeRequest:
    def __init__(self):
        self.accept_format = None
        self.domain_name = None
        self.page_number = None
        self.page_size = None
        self.rr_keyword = None
        self.record_type = None

    def set_accept_format(self, value):
        self.accept_format = value

    def set_DomainName(self, value):
        self.domain_name = value

    def set_PageNumber(self, value):
        self.page_number = value

    def set_PageSize(self, value):
        self.page_size = value

    def set_RRKeyWord(self, value):
        self.rr_keyword = value

    def set_Type(self, value):
        self.record_type = value


class DummyAddRequest:
    def __init__(self):
        self.accept_format = None
        self.domain_name = None
        self.rr = None
        self.record_type = None
        self.value = None
        self.line = None

    def set_accept_format(self, value):
        self.accept_format = value

    def set_DomainName(self, value):
        self.domain_name = value

    def set_RR(self, value):
        self.rr = value

    def set_Type(self, value):
        self.record_type = value

    def set_Value(self, value):
        self.value = value

    def set_Line(self, value):
        self.line = value


class DummyDeleteRequest:
    def __init__(self):
        self.record_id = None

    def set_RecordId(self, value):
        self.record_id = value


class DummyAcsClient:
    def __init__(self, *args, **kwargs):
        pass


def install_aliyun_stubs() -> None:
    sys.modules["aliyunsdkcore"] = types.ModuleType("aliyunsdkcore")
    client_module = types.ModuleType("aliyunsdkcore.client")
    setattr(client_module, "AcsClient", DummyAcsClient)
    sys.modules["aliyunsdkcore.client"] = client_module

    sys.modules["aliyunsdkalidns"] = types.ModuleType("aliyunsdkalidns")
    sys.modules["aliyunsdkalidns.request"] = types.ModuleType("aliyunsdkalidns.request")
    sys.modules["aliyunsdkalidns.request.v20150109"] = types.ModuleType("aliyunsdkalidns.request.v20150109")

    add_module = types.ModuleType("aliyunsdkalidns.request.v20150109.AddDomainRecordRequest")
    setattr(add_module, "AddDomainRecordRequest", DummyAddRequest)
    delete_module = types.ModuleType("aliyunsdkalidns.request.v20150109.DeleteDomainRecordRequest")
    setattr(delete_module, "DeleteDomainRecordRequest", DummyDeleteRequest)
    describe_module = types.ModuleType("aliyunsdkalidns.request.v20150109.DescribeDomainRecordsRequest")
    setattr(describe_module, "DescribeDomainRecordsRequest", DummyDescribeRequest)

    sys.modules[add_module.__name__] = add_module
    sys.modules[delete_module.__name__] = delete_module
    sys.modules[describe_module.__name__] = describe_module


install_aliyun_stubs()
cf2alidns = importlib.import_module("src.cf2alidns")


class FakeClient:
    def __init__(self):
        self.calls = []

    def do_action_with_exception(self, request):
        self.calls.append(request)
        return b"{}"


class Cf2AliDnsTests(unittest.TestCase):
    def test_update_aliyun_dns_records_deletes_oldest_before_add_when_line_full(self):
        fake_client = FakeClient()
        existing_records = [
            {
                "RR": "www",
                "Line": "mobile",
                "Value": "1.1.1.1",
                "RecordId": "record-old",
                "CreateTimestamp": 1,
            }
        ]

        with patch.object(cf2alidns, "get_client", return_value=fake_client), \
             patch.object(cf2alidns, "get_package_num", return_value=1), \
             patch.object(cf2alidns, "query_all_domain_records", return_value=existing_records):
            cf2alidns.update_aliyun_dns_records(
                domain_rr="www",
                domain_root="example.com",
                ips_by_carrier={"mobile": ["2.2.2.2"]},
            )

        self.assertEqual(len(fake_client.calls), 2)
        self.assertIsInstance(fake_client.calls[0], DummyDeleteRequest)
        self.assertEqual(fake_client.calls[0].record_id, "record-old")
        self.assertIsInstance(fake_client.calls[1], DummyAddRequest)
        self.assertEqual(fake_client.calls[1].domain_name, "example.com")
        self.assertEqual(fake_client.calls[1].rr, "www")
        self.assertEqual(fake_client.calls[1].value, "2.2.2.2")
        self.assertEqual(fake_client.calls[1].line, "mobile")

    def test_delete_record_by_value_deletes_matching_record(self):
        fake_client = FakeClient()
        existing_records = [
            {
                "RR": "www",
                "Line": "mobile",
                "Type": "A",
                "Value": "2.2.2.2",
                "RecordId": "record-target",
            }
        ]

        with patch.object(cf2alidns, "get_client", return_value=fake_client), \
             patch.object(cf2alidns, "query_all_domain_records", return_value=existing_records):
            cf2alidns.delete_record_by_value("example.com", "www", "2.2.2.2", "mobile")

        self.assertEqual(len(fake_client.calls), 1)
        self.assertIsInstance(fake_client.calls[0], DummyDeleteRequest)
        self.assertEqual(fake_client.calls[0].record_id, "record-target")

    def test_sync_aliyun_dns_records_exact_replaces_stale_temp_records(self):
        fake_client = FakeClient()
        existing_records = [
            {"RR": "temp", "Line": "mobile", "Type": "A", "Value": "1.1.1.1", "RecordId": "record-old"}
        ]

        with patch.object(cf2alidns, "get_client", return_value=fake_client), \
             patch.object(cf2alidns, "query_all_domain_records", return_value=existing_records):
            cf2alidns.sync_aliyun_dns_records_exact(
                domain_rr="temp",
                domain_root="example.com",
                ips_by_carrier={"mobile": ["2.2.2.2"]},
            )

        self.assertEqual(len(fake_client.calls), 2)
        self.assertIsInstance(fake_client.calls[0], DummyDeleteRequest)
        self.assertIsInstance(fake_client.calls[1], DummyAddRequest)
        self.assertEqual(fake_client.calls[1].rr, "temp")
        self.assertEqual(fake_client.calls[1].value, "2.2.2.2")

    def test_ensure_production_dns_records_adds_only_until_target(self):
        fake_client = FakeClient()
        existing_records = [
            {"RR": "www", "Line": "mobile", "Type": "A", "Value": "1.1.1.1", "RecordId": "record-1"}
        ]

        with patch.object(cf2alidns, "get_client", return_value=fake_client), \
             patch.object(cf2alidns, "query_all_domain_records", return_value=existing_records):
            cf2alidns.ensure_production_dns_records(
                domain_rr="www",
                domain_root="example.com",
                ips_by_carrier={"mobile": ["2.2.2.2", "3.3.3.3", "4.4.4.4"]},
                floor_count=2,
                target_count=3,
                ceiling_count=5,
            )

        add_calls = [call for call in fake_client.calls if isinstance(call, DummyAddRequest)]
        self.assertEqual(len(add_calls), 2)
        self.assertEqual([call.value for call in add_calls], ["2.2.2.2", "3.3.3.3"])

    def test_prune_production_dns_records_deletes_oldest_non_preferred_records(self):
        fake_client = FakeClient()
        existing_records = [
            {"RR": "www", "Line": "mobile", "Type": "A", "Value": "1.1.1.1", "RecordId": "record-1", "CreateTimestamp": 1},
            {"RR": "www", "Line": "mobile", "Type": "A", "Value": "2.2.2.2", "RecordId": "record-2", "CreateTimestamp": 2},
            {"RR": "www", "Line": "mobile", "Type": "A", "Value": "3.3.3.3", "RecordId": "record-3", "CreateTimestamp": 3},
            {"RR": "www", "Line": "mobile", "Type": "A", "Value": "4.4.4.4", "RecordId": "record-4", "CreateTimestamp": 4},
        ]

        with patch.object(cf2alidns, "get_client", return_value=fake_client), \
             patch.object(cf2alidns, "query_all_domain_records", return_value=existing_records):
            pruned = cf2alidns.prune_production_dns_records(
                domain_rr="www",
                domain_root="example.com",
                preferred_ips_by_carrier={"mobile": ["4.4.4.4"]},
                floor_count=1,
                ceiling_count=2,
                max_prune_per_line=2,
            )

        self.assertEqual([item["ip"] for item in pruned], ["1.1.1.1", "2.2.2.2"])
        delete_calls = [call for call in fake_client.calls if isinstance(call, DummyDeleteRequest)]
        self.assertEqual([call.record_id for call in delete_calls], ["record-1", "record-2"])


if __name__ == "__main__":
    unittest.main()
