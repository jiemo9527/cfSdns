import sys
import types
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

cloudscraper_module = types.ModuleType("cloudscraper")
setattr(cloudscraper_module, "create_scraper", lambda: None)
sys.modules.setdefault("cloudscraper", cloudscraper_module)

getv3data_stub = types.ModuleType("src.getv3data")
setattr(getv3data_stub, "v3data", lambda: ([], [], []))
sys.modules.setdefault("src.getv3data", getv3data_stub)

from src.getIPFromW3 import (
    classify_api_ip_data,
    parse_cf090227_domain_cards,
    parse_table_ips_from_html,
    parse_text_ips,
)

sys.modules.pop("src.getv3data", None)


class ApiParserTests(unittest.TestCase):
    def test_classify_api_ip_data_uses_packet_loss_thresholds(self):
        payload = {
            "data": {
                "providerA": [
                    {
                        "ip": "104.16.1.1",
                        "ydPkgLostRateAvg": 1.0,
                        "ltPkgLostRateAvg": 0.1,
                        "dxPkgLostRateAvg": 2.0,
                    },
                    {
                        "ip": "104.16.1.2",
                        "ydPkgLostRateAvg": 4.0,
                        "ltPkgLostRateAvg": 0.1,
                        "dxPkgLostRateAvg": 2.0,
                    },
                ]
            }
        }

        mobile, unicom, telecom = classify_api_ip_data(payload)

        self.assertEqual(mobile, ["104.16.1.1"])
        self.assertEqual(unicom, ["104.16.1.1", "104.16.1.2"])
        self.assertEqual(telecom, ["104.16.1.1", "104.16.1.2"])


class HtmlParserTests(unittest.TestCase):
    def test_parse_table_ips_from_html_classifies_carriers(self):
        html = """
        <table>
            <tr><td>移动优选</td><td>104.16.1.1</td></tr>
            <tr><td>联通优选</td><td>104.16.1.2</td></tr>
            <tr><td>电信优选</td><td>104.16.1.3</td></tr>
            <tr><td>移动异常</td><td>not-an-ip</td></tr>
        </table>
        """

        mobile, unicom, telecom = parse_table_ips_from_html(html)

        self.assertEqual(mobile, ["104.16.1.1"])
        self.assertEqual(unicom, ["104.16.1.2"])
        self.assertEqual(telecom, ["104.16.1.3"])

    def test_parse_text_ips_filters_invalid_entries(self):
        text = "104.16.1.1, invalid, 172.16.0.1,104.16.1.2"

        result = parse_text_ips(text)

        self.assertEqual(result, ["104.16.1.1", "104.16.1.2"])

    def test_parse_cf090227_domain_cards_extracts_hosts_and_carriers(self):
        html = """
        <div class="domain-card">
            <div>三网优选</div>
            <a class="test-link" href="https://www.itdog.cn/tcping/cf.example.com:443">TCPing</a>
        </div>
        <div class="domain-card">
            <div>中国移动 专属优选</div>
            <a class="test-link" href="https://www.itdog.cn/tcping/mobile.example.com:443">TCPing</a>
        </div>
        """

        result = parse_cf090227_domain_cards(html)

        self.assertEqual(
            result,
            [
                ("cf.example.com", ["mobile", "unicom", "telecom"]),
                ("mobile.example.com", ["mobile"]),
            ],
        )


if __name__ == "__main__":
    unittest.main()
