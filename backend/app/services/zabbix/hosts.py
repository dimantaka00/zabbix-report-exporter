# backend/app/services/zabbix/hosts.py

class ZabbixHostService:

    def __init__(self, client):
        self.client = client

    async def get_hosts(self):

        return await self.client.call(
            "host.get",
            {
                "output": [
                    "hostid",
                    "host",
                    "name",
                    "status"
                ],
                "selectInterfaces": [
                    "interfaceid",
                    "ip",
                    "dns"
                ]
            }
        )