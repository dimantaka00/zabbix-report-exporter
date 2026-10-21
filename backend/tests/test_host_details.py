import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from app.api.v1 import zabbix
from app.services.zabbix.client import ZabbixClient


class HostDetailsTests(unittest.IsolatedAsyncioTestCase):
    def client(self, version, responses):
        client = ZabbixClient.__new__(ZabbixClient)
        client.api_version = AsyncMock(return_value=version)
        client.call = AsyncMock(side_effect=responses)
        return client

    def host(self, **fields):
        return {"hostid": "1", "host": "router", "name": "Router DC", "status": "1",
                "description": "Core router\nData center", "interfaces": [],
                "parentTemplates": [{"templateid": "20", "name": "Network template"}], **fields}

    async def test_legacy_and_modern_group_selectors_and_proxy_names(self):
        for version in ("6.0.42", "6.2.9", "6.4.21", "7.0.20", "7.4.10"):
            with self.subTest(version=version):
                modern = version.startswith("7.")
                legacy_groups = version.startswith("6.0")
                host = self.host(**{
                    "groups" if legacy_groups else "hostgroups": [{"groupid": "5", "name": "Routers"}],
                    "proxyid" if modern else "proxy_hostid": "8", "monitored_by": "1"})
                client = self.client(version, [[host], [{"proxyid": "8", "name" if modern else "host": "Proxy DC"}]])
                result = await client.get_host_details("1")
                request = client.call.call_args_list[0].args[1]
                self.assertIn("selectGroups" if legacy_groups else "selectHostGroups", request)
                self.assertNotIn("selectHostGroups" if legacy_groups else "selectGroups", request)
                self.assertIn("proxyid" if modern else "proxy_hostid", request["output"])
                self.assertNotIn("proxy_hostid" if modern else "proxyid", request["output"])
                self.assertEqual(request["hostids"], ["1"])
                self.assertEqual(result["proxy"]["name"], "Proxy DC")
                self.assertEqual(result["groups"], [{"groupid": "5", "name": "Routers"}])
                self.assertEqual(result["templates"][0]["name"], "Network template")
                self.assertEqual(result["status"], "1")  # Disabled hosts remain inspectable.

    async def test_snmp_whitelist_preserves_interfaces_but_excludes_credentials(self):
        interfaces = [
            {"interfaceid": "10", "type": "2", "main": "1", "ip": "10.0.0.1", "dns": "", "useip": "1",
             "port": "161", "available": "1", "error": "private error",
             "details": {"version": "3", "bulk": "1", "securitylevel": "2", "community": "private-community",
                         "securityname": "private-user", "authpassphrase": "private-auth", "privpassphrase": "private-privacy"}},
            {"interfaceid": "11", "type": "1", "main": "1", "ip": "", "dns": "agent.example", "useip": "0",
             "port": "{$AGENT_PORT}", "available": "0", "details": {"community": "another-secret"}},
        ]
        client = self.client("7.4.10", [[self.host(interfaces=interfaces, monitored_by="0")]])
        result = await client.get_host_details("1")
        self.assertEqual(result["interfaces"][0]["snmp"], {"version": "3", "bulk": "1", "securitylevel": "2"})
        self.assertIsNone(result["interfaces"][1]["snmp"])
        self.assertEqual(result["interfaces"][1]["port"], "{$AGENT_PORT}")
        self.assertEqual(result["interfaces"][1]["dns"], "agent.example")
        for secret in ("private-community", "private-user", "private-auth", "private-privacy", "another-secret", "private error"):
            self.assertNotIn(secret, json.dumps(result))
        self.assertEqual(client.call.await_count, 1)  # Server monitoring needs no proxy lookup.
        self.assertEqual(result["proxy"]["mode"], "server")

    async def test_proxy_group_and_assigned_proxy(self):
        client = self.client("7.0.20", [[self.host(monitored_by="2", proxy_groupid="4", assigned_proxyid="8")],
                                      [{"proxy_groupid": "4", "name": "DC group"}], [{"proxyid": "8", "name": "DC proxy"}]])
        result = await client.get_host_details("1")
        self.assertEqual(result["proxy"], {"mode": "proxy_group", "id": "4", "name": "DC group",
                                          "assigned_proxy": {"id": "8", "name": "DC proxy"}})
        self.assertEqual(client.call.call_args_list[1].args[1]["proxy_groupids"], ["4"])

    async def test_restricted_proxy_lookup_preserves_host_and_sanitizes_error(self):
        for failure in (RuntimeError("secret upstream details"), []):
            with self.subTest(failure=type(failure).__name__):
                client = self.client("6.0.42", [[self.host(proxy_hostid="8")], failure])
                result = await client.get_host_details("1")
                self.assertEqual(result["name"], "Router DC")
                self.assertEqual(result["proxy"]["id"], "8")
                self.assertIsNone(result["proxy"]["name"])
                self.assertEqual(len(result["warnings"]), 1)
                self.assertNotIn("secret upstream", json.dumps(result))

    async def test_missing_inaccessible_or_mismatched_host_is_rejected(self):
        for response in ([], [self.host(hostid="2")], [self.host(), self.host()]):
            with self.subTest(response=response):
                client = self.client("7.4.10", [response])
                with self.assertRaisesRegex(ValueError, "Host tidak ditemukan"):
                    await client.get_host_details("1")

    async def test_invalid_id_is_rejected_before_api_call(self):
        for hostid in ("", "-1", "1/2", "１２", "9" * 33):
            with self.subTest(hostid=hostid):
                client = self.client("7.4.10", [])
                with self.assertRaisesRegex(ValueError, "ID host tidak valid"):
                    await client.get_host_details(hostid)
                client.api_version.assert_not_awaited()
                client.call.assert_not_awaited()

    async def test_endpoint_uses_selected_server(self):
        client = MagicMock(get_host_details=AsyncMock(return_value={"hostid": "1"}))
        with patch.object(zabbix, "ZabbixClient", return_value=client) as factory:
            result = await zabbix.host_details("1", "secondary")
        factory.assert_called_once_with("secondary")
        client.get_host_details.assert_awaited_once_with("1")
        self.assertEqual(result, {"success": True, "data": {"hostid": "1"}})
