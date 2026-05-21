import asyncio
import aiohttp
import json

async def test_auth():
    async with aiohttp.ClientSession() as session:
        print("Registering new user...")
        async with session.post('http://localhost:8765/api/register', json={
            'username': 'schema_test1',
            'display_name': 'Test1',
            'password': 'password123'
        }) as r:
            body = await r.json()
            if r.status != 200:
                print("Register error:", r.status, body)
                return
            token = body['token']
            print("Token:", token)
            
        print("Fetching rooms...")
        async with session.get('http://localhost:8765/api/rooms', headers={'Authorization': f'Bearer {token}'}) as r2:
            print("Rooms Response:", r2.status, await r2.text())
            
        print("Fetching search...")
        async with session.get('http://localhost:8765/api/search?q=', headers={'Authorization': f'Bearer {token}'}) as r3:
            print("Search Response:", r3.status, await r3.text())

asyncio.run(test_auth())
