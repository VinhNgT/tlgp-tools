import asyncio
import json
import time
import subprocess
import websockets
import sys
import httpx
from uuid import uuid4
import os

PORT = 8089
WS_URL = f"ws://localhost:{PORT}/ws"
REST_URL = f"http://localhost:{PORT}"
NUM_CLIENTS = 10
MUTATIONS_PER_CLIENT = 10

async def client_task(client_id, ready_event, start_event, stats):
    try:
        async with websockets.connect(WS_URL, open_timeout=10, ping_timeout=None) as ws:
            # Receive full sync
            full_sync = json.loads(await ws.recv())
            
            ready_event.set()
            await start_event.wait()
            
            # Fire mutations
            for i in range(MUTATIONS_PER_CLIENT):
                req = {
                    "jsonrpc": "2.0",
                    "method": "add_component",
                    "params": {
                        "id": str(uuid4()),
                        "label": f"Comp {client_id}-{i}",
                        "bounds": {"x": 10, "y": 10, "w": 100, "h": 100}
                    },
                    "id": f"{client_id}-{i}"
                }
                await ws.send(json.dumps(req))
                
            patches_received = 0
            rpc_responses = 0
            expected_patches = NUM_CLIENTS * MUTATIONS_PER_CLIENT
            
            while patches_received < expected_patches or rpc_responses < MUTATIONS_PER_CLIENT:
                msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=10.0))
                if "type" in msg and msg["type"] == "patch":
                    patches_received += 1
                elif "jsonrpc" in msg:
                    rpc_responses += 1
                    if "error" in msg:
                        print(f"RPC Error: {msg['error']}")
                if (patches_received + rpc_responses) % 500 == 0:
                    print(f"Client {client_id} received {patches_received} patches and {rpc_responses} rpc responses")
                    
            stats["success"] += 1
    except Exception as e:
        print(f"Client {client_id} failed: {e}")


async def main():
    print(f"Starting uvicorn on port {PORT}...")
    # Run uvicorn inside the apps/engine directory
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "engine.app:app", "--port", str(PORT)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        cwd=os.path.join(os.path.dirname(__file__), "..", "src")
    )
    
    try:
        # Wait for server
        for _ in range(20):
            try:
                async with httpx.AsyncClient() as client:
                    res = await client.get(f"{REST_URL}/state")
                    if res.status_code == 200:
                        break
            except Exception:
                await asyncio.sleep(0.2)
        else:
            print("Server failed to start.")
            return

        # Setup image so mutations work
        print("Setting up image...")
        dummy_path = os.path.join(os.path.dirname(__file__), "dummy.png")
        with open(dummy_path, "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\x0bIDAT\x08\xd7c\xf8\xff\xff\x3f\x00\x05\xfe\x02\xfe\xa7\x35\x81\x84\x00\x00\x00\x00IEND\xaeB`\x82")
            
        async with httpx.AsyncClient() as client:
            with open(dummy_path, "rb") as f:
                await client.post(f"{REST_URL}/import/image", files={"file": ("dummy.png", f, "image/png")})

        print("Spawning clients...")
        ready_events = [asyncio.Event() for _ in range(NUM_CLIENTS)]
        start_event = asyncio.Event()
        stats = {"success": 0}
        
        tasks = []
        for i in range(NUM_CLIENTS):
            tasks.append(asyncio.create_task(client_task(i, ready_events[i], start_event, stats)))
            
        # Wait for all to connect
        await asyncio.gather(*[e.wait() for e in ready_events])
        
        print(f"All {NUM_CLIENTS} clients connected. Firing mutations...")
        start_time = time.time()
        start_event.set()
        
        # Wait for all to finish
        await asyncio.gather(*tasks)
        
        duration = time.time() - start_time
        print(f"Completed in {duration:.2f} seconds.")
        print(f"Clients successful: {stats['success']}/{NUM_CLIENTS}")
    finally:
        server.terminate()
        try:
            os.remove(dummy_path)
        except Exception:
            pass

if __name__ == "__main__":
    asyncio.run(main())
