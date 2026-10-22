import os
import unittest

import openvpn_addon as addon


class OpenVPNAddonValidationTests(unittest.TestCase):
    def test_username_allowlist(self):
        for good in ("user_01", "User-22", "ab"):
            self.assertEqual(addon._username(good), good)
        for bad in ("a", "../root", "server", "ca", "bad name", "x;id", "x/../y"):
            with self.assertRaises(Exception):
                addon._username(bad)

    def test_public_host_validation(self):
        old = os.environ.get("SPIDER_OPENVPN_PUBLIC_HOST")
        try:
            for host in ("vpn.example.com", "203.0.113.15"):
                os.environ["SPIDER_OPENVPN_PUBLIC_HOST"] = host
                self.assertEqual(addon._public_host(), host)
            for host in ("", "localhost", "https://vpn.example.com", "a..b", "host:1194", "x/y"):
                os.environ["SPIDER_OPENVPN_PUBLIC_HOST"] = host
                self.assertEqual(addon._public_host(), "")
        finally:
            if old is None:
                os.environ.pop("SPIDER_OPENVPN_PUBLIC_HOST", None)
            else:
                os.environ["SPIDER_OPENVPN_PUBLIC_HOST"] = old

    def test_control_command_never_uses_shell(self):
        old_sudo = os.environ.get("SPIDER_OPENVPN_USE_SUDO")
        old_ctl = os.environ.get("SPIDER_OPENVPN_CTL")
        try:
            os.environ["SPIDER_OPENVPN_USE_SUDO"] = "0"
            os.environ["SPIDER_OPENVPN_CTL"] = "/usr/local/sbin/spider-openvpnctl"
            cmd = addon._control_command("create", "user_01")
            self.assertEqual(cmd[0], "/usr/local/sbin/spider-openvpnctl")
            self.assertEqual(cmd[1:], ["create", "user_01"])
        finally:
            if old_sudo is None:
                os.environ.pop("SPIDER_OPENVPN_USE_SUDO", None)
            else:
                os.environ["SPIDER_OPENVPN_USE_SUDO"] = old_sudo
            if old_ctl is None:
                os.environ.pop("SPIDER_OPENVPN_CTL", None)
            else:
                os.environ["SPIDER_OPENVPN_CTL"] = old_ctl


if __name__ == "__main__":
    unittest.main()
