"""Проверки реального HTTP-парсера; соединения только с локальным стендом."""
import asyncio
import gzip
import unittest

import aiohttp


class TransportTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tasks = set()
        self.response = b""
        self.delay = 0
        self.server = await asyncio.start_server(self.serve, "127.0.0.1", 0)
        self.url = f"http://127.0.0.1:{self.server.sockets[0].getsockname()[1]}/"

    async def serve(self, reader, writer):
        task = asyncio.current_task()
        self.tasks.add(task)
        try:
            await reader.readuntil(b"\r\n\r\n")
            await asyncio.sleep(self.delay)
            writer.write(self.response)
            await writer.drain()
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        finally:
            writer.close()
            await writer.wait_closed()
            self.tasks.discard(task)

    async def asyncTearDown(self):
        self.server.close()
        await self.server.wait_closed()
        for task in list(self.tasks):
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)

    def reply(self, body=b"ok", headers=b"", status=b"200 OK"):
        self.response = (b"HTTP/1.1 " + status + b"\r\nContent-Length: "
                         + str(len(body)).encode() + b"\r\nConnection: close\r\n"
                         + headers + b"\r\n" + body)

    async def test_valid_gzip_and_cookie(self):
        self.reply(gzip.compress(b"expected"), b"Content-Encoding: gzip\r\nSet-Cookie: session=valid; Path=/\r\n")
        async with aiohttp.ClientSession(trust_env=False) as session:
            async with session.get(self.url) as response:
                self.assertEqual(await response.read(), b"expected")
                self.assertEqual(response.cookies["session"].value, "valid")

    async def test_excessive_gzip_members_rejected(self):
        # Малый ограниченный образец проверяет защиту без истощения ресурсов.
        self.reply(gzip.compress(b"x") * 1025, b"Content-Encoding: gzip\r\n")
        async with aiohttp.ClientSession(trust_env=False) as session:
            with self.assertRaises(aiohttp.ClientPayloadError):
                async with session.get(self.url) as response:
                    await response.read()

    async def test_cookie_jar_bounded_with_ordinary_control(self):
        # unsafe разрешает только cookies IP-адреса локального стенда.
        jar = aiohttp.CookieJar(unsafe=True)
        async with aiohttp.ClientSession(cookie_jar=jar, trust_env=False) as session:
            for offset in range(0, 200, 50):
                headers = b"".join(f"Set-Cookie: c{i}=v; Path=/\r\n".encode() for i in range(offset, offset + 50))
                self.reply(headers=headers)
                async with session.get(self.url) as response:
                    await response.read()
            self.assertGreater(len(jar), 0)
            self.assertLessEqual(len(jar), 180)

    async def test_timeout_then_next_request_succeeds(self):
        self.reply()
        self.delay = 0.2
        async with aiohttp.ClientSession(trust_env=False) as session:
            with self.assertRaises(asyncio.TimeoutError):
                await session.get(self.url, timeout=aiohttp.ClientTimeout(total=0.02))
            self.delay = 0
            async with session.get(self.url) as response:
                self.assertEqual(await response.read(), b"ok")

    async def test_truncated_payload_is_error(self):
        self.response = b"HTTP/1.1 200 OK\r\nContent-Length: 20\r\nConnection: close\r\n\r\nshort"
        async with aiohttp.ClientSession(trust_env=False) as session:
            with self.assertRaises(aiohttp.ClientPayloadError):
                async with session.get(self.url) as response:
                    await response.read()

    async def test_http_error_remains_visible(self):
        self.reply(status=b"503 Service Unavailable")
        async with aiohttp.ClientSession(trust_env=False) as session:
            async with session.get(self.url) as response:
                with self.assertRaises(aiohttp.ClientResponseError) as raised:
                    response.raise_for_status()
                self.assertEqual(raised.exception.status, 503)
