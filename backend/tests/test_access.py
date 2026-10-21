import asyncio
import os
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from starlette.requests import Request

from app.core import database
from app.core.config import settings
from app.services import access


class AccessUnitTests(unittest.IsolatedAsyncioTestCase):
    async def test_password_hash_and_unknown_hash(self):
        encoded=access.password_hash('test-password-long')
        self.assertNotIn('test-password-long',encoded)
        self.assertTrue(access.verify_password('test-password-long',encoded))
        self.assertFalse(access.verify_password('wrong',encoded))
        self.assertFalse(access.verify_password('wrong','bad hash'))
        self.assertNotEqual(encoded,access.password_hash('test-password-long'))

    async def test_untrusted_peer_cannot_spoof_client_ip(self):
        scope={'type':'http','method':'GET','path':'/','query_string':b'', 'scheme':'http',
            'server':('test',80),'client':('10.0.0.8',1),'headers':[(b'x-real-ip',b'8.8.8.8'),(b'x-forwarded-for',b'8.8.8.8')]}
        with patch.object(access,'trusted_proxy',return_value=False):
            d=await access.client_details(Request(scope))
        self.assertEqual(d['ip'],'10.0.0.8')
        self.assertEqual(d['ip_kind'],'internal')
        with patch.object(access,'trusted_proxy',return_value=True),patch.object(settings,'GEOIP_DATABASE','/no/database'):
            d=await access.client_details(Request(scope))
        self.assertEqual(d['ip'],'8.8.8.8')
        self.assertEqual(d['country_name'],'Tidak diketahui')

    async def test_private_and_ipv6_addresses_are_not_guessed_as_a_country(self):
        for ip in ('127.0.0.1','192.168.1.1','10.0.0.1','::1','fd00::1'):
            self.assertIsNone(access.country_for(ip)['country_code'])
            self.assertEqual(access.country_for(ip)['ip_kind'],'internal')


@unittest.skipUnless(os.getenv('TEST_DATABASE_URL'),'Requires a disposable PostgreSQL database')
class AccessIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.patch=patch.object(database,'DATABASE_URL',os.environ['TEST_DATABASE_URL']);self.patch.start()
        await database.init_db();self.pool=database.get_pool()
        await self.pool.execute('TRUNCATE app_sessions,access_events,app_users RESTART IDENTITY CASCADE')
        self.password='integration-password-long'
        for name,role,must_change in [('admin','admin',False),('operator','operator',False),('newuser','operator',True)]:
            await self.pool.execute("""INSERT INTO app_users(username,display_name,password_hash,role,must_change_password)
                VALUES($1,$1,$2,$3,$4)""",name,access.password_hash(self.password),role,must_change)
        from app.main import app
        self.http=httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test')

    async def asyncTearDown(self):
        await self.http.aclose();await database.close_db();self.patch.stop()

    async def login(self,name='admin'):
        response=await self.http.post('/api/v1/auth/login',json={'username':name,'password':self.password})
        self.assertEqual(response.status_code,200,response.text)
        self.http.headers['X-CSRF-Token']=response.json()['data']['csrf_token']
        return response

    async def test_anonymous_api_and_pdf_access_denied(self):
        for path in ('/api/v1/schedules','/api/v1/history','/api/v1/reports/missing.pdf','/api/v1/admin/summary'):
            self.assertEqual((await self.http.get(path)).status_code,401)
        self.assertEqual((await self.http.get('/health/ready')).status_code,200)

    async def test_disabled_login_opens_business_routes_but_keeps_admin_private(self):
        users_before=await self.pool.fetchval('SELECT COUNT(*) FROM app_users')
        with patch.object(settings,'AUTH_ENABLED',False):
            for path in ('/api/v1/schedules','/api/v1/history','/api/v1/reports'):
                self.assertEqual((await self.http.get(path)).status_code,200)
            self.assertEqual((await self.http.get('/api/v1/reports/missing.pdf')).status_code,404)
            self.assertEqual((await self.http.get('/api/v1/auth/check')).status_code,204)
            response=await self.http.get('/api/v1/auth/me')
            self.assertEqual(response.json()['data'],{'authentication_enabled':False})
            self.assertIn('no-store',response.headers['cache-control'])
            for path in ('/api/v1/admin/summary','/api/v1/admin/users','/api/v1/admin/events','/api/v1/admin/sessions'):
                self.assertEqual((await self.http.get(path)).status_code,403)
            self.assertEqual((await self.http.post('/api/v1/auth/login',json={'username':'admin','password':self.password})).status_code,403)
            self.assertEqual((await self.http.post('/api/v1/admin/users',json={})).status_code,403)
        self.assertEqual(await self.pool.fetchval('SELECT COUNT(*) FROM app_users'),users_before)
        self.assertEqual((await self.http.get('/api/v1/schedules')).status_code,401)

    async def test_disabled_login_also_blocks_preexisting_admin_sessions(self):
        await self.login()
        sessions_before=await self.pool.fetchval('SELECT COUNT(*) FROM app_sessions')
        with patch.object(settings,'AUTH_ENABLED',False):
            self.assertEqual((await self.http.get('/api/v1/admin/events')).status_code,403)
            self.assertEqual((await self.http.post('/api/v1/auth/password',json={})).status_code,403)
            self.assertEqual((await self.http.get('/api/v1/auth/me')).json()['data'],{'authentication_enabled':False})
        self.assertEqual(await self.pool.fetchval('SELECT COUNT(*) FROM app_sessions'),sessions_before)
        self.assertEqual((await self.http.get('/api/v1/admin/events')).status_code,200)

    async def test_session_cookie_is_opaque_and_logout_revokes_it(self):
        response=await self.login()
        cookie=response.headers['set-cookie']
        self.assertIn('HttpOnly',cookie);self.assertIn('SameSite=lax',cookie)
        token=self.http.cookies[access.COOKIE]
        stored=await self.pool.fetchval('SELECT token_hash FROM app_sessions LIMIT 1')
        self.assertEqual(stored,access.token_hash(token));self.assertNotEqual(stored,token)
        self.assertEqual((await self.http.get('/api/v1/auth/me')).status_code,200)
        self.assertEqual((await self.http.post('/api/v1/auth/logout')).status_code,200)
        self.assertEqual((await self.http.get('/api/v1/auth/me')).status_code,401)

    async def test_csrf_and_foreign_origin_rejected_before_writes(self):
        await self.login()
        self.assertEqual((await self.http.post('/api/v1/auth/visit',json={'path':'/'},headers={'X-CSRF-Token':''})).status_code,403)
        self.assertEqual((await self.http.post('/api/v1/auth/visit',json={'path':'/'},headers={'Origin':'https://evil.invalid'})).status_code,403)
        self.assertEqual((await self.http.post('/api/v1/auth/visit',json={'path':'/'},headers={'Origin':'http://test'})).status_code,200)

    async def test_operator_cannot_read_or_mutate_admin_resources(self):
        await self.login('operator')
        for path in ('/api/v1/admin/summary','/api/v1/admin/events','/api/v1/admin/users','/api/v1/admin/sessions'):
            self.assertEqual((await self.http.get(path)).status_code,403)
        self.assertEqual((await self.http.post('/api/v1/admin/users',json={})).status_code,403)

    async def test_failed_login_logged_and_limited_without_leaking_password(self):
        for _ in range(8):
            self.assertEqual((await self.http.post('/api/v1/auth/login',json={'username':'admin','password':'wrong'})).status_code,401)
        self.assertEqual((await self.http.post('/api/v1/auth/login',json={'username':'admin','password':self.password})).status_code,429)
        events=await self.pool.fetch("SELECT * FROM access_events WHERE event_type='login_failed'")
        self.assertEqual(len(events),8);self.assertNotIn('wrong',str(events))
        self.assertTrue(all(row['ip']=='127.0.0.1' for row in events))

    async def test_concurrent_failed_logins_cannot_bypass_limit(self):
        responses=await asyncio.gather(*(self.http.post('/api/v1/auth/login',json={'username':'admin','password':'wrong'}) for _ in range(12)))
        self.assertEqual(sum(r.status_code==401 for r in responses),8)
        self.assertEqual(sum(r.status_code==429 for r in responses),4)

    async def test_temporary_password_requires_change_and_rotates_session(self):
        await self.login('newuser');old_token=self.http.cookies[access.COOKIE]
        self.assertEqual((await self.http.get('/api/v1/schedules')).status_code,403)
        response=await self.http.post('/api/v1/auth/password',json={'current_password':self.password,'password':'changed-password-long'})
        self.assertEqual(response.status_code,200,response.text)
        self.assertFalse(response.json()['data']['must_change_password'])
        self.assertNotEqual(self.http.cookies[access.COOKIE],old_token)
        self.assertFalse(await self.pool.fetchval('SELECT EXISTS(SELECT 1 FROM app_sessions WHERE token_hash=$1)',access.token_hash(old_token)))
        self.assertEqual((await self.http.get('/api/v1/schedules')).status_code,200)

    async def test_admin_create_disable_reset_and_revoke_are_effective(self):
        await self.login()
        response=await self.http.post('/api/v1/admin/users',json={'username':'member','display_name':'Member','role':'operator','password':'member-password-long'})
        self.assertEqual(response.status_code,200,response.text)
        user_id=response.json()['data']['id']
        self.assertEqual((await self.http.patch(f'/api/v1/admin/users/{user_id}/status',json={'active':False})).status_code,200)
        self.assertEqual((await self.http.post('/api/v1/auth/login',json={'username':'member','password':'member-password-long'})).status_code,401)
        self.assertEqual((await self.http.post(f'/api/v1/admin/users/{user_id}/password',json={'password':'reset-password-long'})).status_code,200)
        self.assertEqual((await self.http.patch('/api/v1/admin/users/1/status',json={'active':False})).status_code,400)
        session=await self.pool.fetchval('SELECT id FROM app_sessions WHERE user_id=1 LIMIT 1')
        self.assertEqual((await self.http.delete(f'/api/v1/admin/sessions/{session}')).status_code,200)
        self.assertEqual((await self.http.get('/api/v1/admin/users')).status_code,401)

    async def test_admin_audit_filters_summary_and_private_details(self):
        await self.login()
        await self.http.post('/api/v1/auth/visit',json={'path':'/admin'})
        response=await self.http.get('/api/v1/admin/events?event_type=page_view&q=admin&limit=1')
        self.assertEqual(response.json()['total'],1)
        self.assertEqual(response.json()['data'][0]['path'],'/admin')
        self.assertEqual(response.json()['data'][0]['ip'],'127.0.0.1')
        self.assertNotIn('csrf_token',response.text);self.assertNotIn('password_hash',response.text)
        self.assertEqual((await self.http.get('/api/v1/admin/summary')).json()['data']['successful_logins'],1)
        session_data=(await self.http.get('/api/v1/admin/sessions')).text
        self.assertNotIn('token_hash',session_data);self.assertNotIn('csrf_token',session_data)

    async def test_bootstrap_is_idempotent_and_does_not_reset_passwords(self):
        before=await self.pool.fetchval('SELECT password_hash FROM app_users WHERE id=1')
        await access.initialize_access()
        self.assertEqual(await self.pool.fetchval('SELECT password_hash FROM app_users WHERE id=1'),before)

    async def test_bootstrap_rejects_placeholder_and_requires_a_unique_password(self):
        await self.pool.execute('TRUNCATE app_sessions,app_users RESTART IDENTITY CASCADE')
        for password in ('','short','REPLACE_WITH_A_UNIQUE_LONG_TEMPORARY_PASSWORD'):
            with patch.object(settings,'AUTH_BOOTSTRAP_PASSWORD',password),self.assertRaises(RuntimeError):
                await access.initialize_access()
        self.assertEqual(await self.pool.fetchval('SELECT COUNT(*) FROM app_users'),0)
        with patch.object(settings,'AUTH_BOOTSTRAP_PASSWORD','unique-bootstrap-password'),patch.object(settings,'AUTH_BOOTSTRAP_USERNAME','admin'):
            await access.initialize_access()
        user=await self.pool.fetchrow('SELECT * FROM app_users LIMIT 1')
        self.assertTrue(user['must_change_password']);self.assertEqual(user['role'],'admin')
        self.assertTrue(access.verify_password('unique-bootstrap-password',user['password_hash']))
