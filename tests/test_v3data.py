import importlib
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def install_crypto_stubs() -> None:
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

    def identity_pad(data, block_size):
        return data

    def identity_unpad(data, block_size):
        return data

    setattr(cipher_module, "DES", DummyDES)
    setattr(padding_module, "pad", identity_pad)
    setattr(padding_module, "unpad", identity_unpad)

    sys.modules["Crypto"] = crypto_module
    sys.modules["Crypto.Cipher"] = cipher_module
    sys.modules["Crypto.Util"] = types.ModuleType("Crypto.Util")
    sys.modules["Crypto.Util.Padding"] = padding_module


install_crypto_stubs()
sys.modules.pop("src.getv3data", None)
getv3data = importlib.import_module("src.getv3data")


class V3DataTests(unittest.TestCase):
    def test_decode_v3data_message_uses_decryptor_output(self):
        decrypted_payload = {"content": [{"ip": "104.16.1.1"}]}

        with patch.object(getv3data, "decrypt_response_message", return_value=json.dumps(decrypted_payload)):
            result = getv3data.decode_v3data_message({"code": 0, "message": "encrypted"})

        self.assertEqual(result, decrypted_payload)

    def test_classify_v3data_ips_applies_thresholds(self):
        payload = {
            "content": [
                {
                    "ip": "104.16.1.1",
                    "ydPkgLostRateAvg": 1.0,
                    "ltPkgLostRateAvg": 0.1,
                    "dxPkgLostRateAvg": 2.0,
                },
                {
                    "ip": "104.16.1.2",
                    "ydPkgLostRateAvg": 4.0,
                    "ltPkgLostRateAvg": 0.3,
                    "dxPkgLostRateAvg": 2.0,
                },
            ]
        }

        mobile, unicom, telecom = getv3data.classify_v3data_ips(payload)

        self.assertEqual(mobile, ["104.16.1.1"])
        self.assertEqual(unicom, ["104.16.1.1"])
        self.assertEqual(telecom, ["104.16.1.1", "104.16.1.2"])

    def test_v3data_returns_classified_result_from_staged_helpers(self):
        with patch.object(getv3data, "fetch_v3data_response", return_value={"code": 0, "message": "x"}), \
             patch.object(getv3data, "decode_v3data_message", return_value={"content": []}), \
             patch.object(getv3data, "classify_v3data_ips", return_value=(['1.1.1.1'], ['2.2.2.2'], ['3.3.3.3'])):
            result = getv3data.v3data()

        self.assertEqual(result, (["1.1.1.1"], ["2.2.2.2"], ["3.3.3.3"]))


if __name__ == "__main__":
    unittest.main()
