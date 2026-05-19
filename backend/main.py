"""
DRIVEWISE — Backend Main Entry Point
WebSocket server streaming live tag data to the React frontend.
Includes test engine and PDF report generation.
"""
import asyncio
import json
import sys
import os

# Add backend dir to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import websockets
from coordinator import SimulationCoordinator
from test_engine import TestEngine
from report_gen import generate_fat_report

# Global state
coordinator = SimulationCoordinator()
test_engine = TestEngine(coordinator)
connected_clients = set()


async def broadcast_tags():
    """Broadcast tag updates to all connected clients at 100ms intervals."""
    while True:
        # Run simulation step (skip if test engine is running its own steps)
        if not test_engine.running:
            coordinator.step()

        # Get all tags
        tags = coordinator.get_all_tags()

        # Broadcast to all connected clients
        if connected_clients:
            message = json.dumps({
                'type': 'tag_update',
                'tags': tags,
            })
            disconnected = set()
            for ws in connected_clients:
                try:
                    await ws.send(message)
                except websockets.exceptions.ConnectionClosed:
                    disconnected.add(ws)
            connected_clients.difference_update(disconnected)

        await asyncio.sleep(0.1)  # 100ms broadcast interval


async def broadcast_message(msg_type, data):
    """Send a message to all connected clients."""
    if connected_clients:
        message = json.dumps({'type': msg_type, **data})
        for ws in list(connected_clients):
            try:
                await ws.send(message)
            except websockets.exceptions.ConnectionClosed:
                connected_clients.discard(ws)


async def handle_command(ws, data):
    """Process a command from the frontend."""
    cmd_type = data.get('type', '')

    if cmd_type == 'start_all':
        coordinator.start_all()
        print(f"[CMD] Start All Sections")

    elif cmd_type == 'stop_all':
        coordinator.stop_all()
        print(f"[CMD] Stop All Sections")

    elif cmd_type == 'estop_all':
        coordinator.estop_all()
        print(f"[CMD] Emergency Stop All")

    elif cmd_type == 'start_section':
        section = data.get('section', 'S1')
        coordinator.start_section(section)
        print(f"[CMD] Start {section}")

    elif cmd_type == 'stop_section':
        section = data.get('section', 'S1')
        coordinator.stop_section(section)
        print(f"[CMD] Stop {section}")

    elif cmd_type == 'estop_section':
        section = data.get('section', 'S1')
        coordinator.estop_section(section)
        print(f"[CMD] E-Stop {section}")

    elif cmd_type == 'set_parameter':
        section = data.get('section', 'S1')
        param = data.get('parameter', '')
        value = data.get('value', '')
        coordinator.set_parameter(section, param, value)
        print(f"[CMD] Set {section}.{param} = {value}")

    elif cmd_type == 'configure':
        coordinator.configure(data)
        print(f"[CMD] Configuration applied")

    elif cmd_type == 'inject_fault':
        section = data.get('section', 'S1')
        fault_type = data.get('fault_type', 'OVERCURRENT')
        unit = coordinator.units.get(section)
        if unit:
            unit.drive.fault(fault_type)
            print(f"[CMD] Fault injected: {section} — {fault_type}")

    elif cmd_type == 'reset_fault':
        section = data.get('section', 'S1')
        unit = coordinator.units.get(section)
        if unit:
            unit.drive.reset_fault()
            unit.prot_overcurrent_trip = False
            unit.prot_overvoltage_trip = False
            unit.prot_undervoltage_trip = False
            unit.prot_earthfault_trip = False
            unit.prot_thermal_trip = False
            unit.overcurrent_timer = 0.0
            print(f"[CMD] Fault reset: {section}")

    elif cmd_type == 'run_test':
        test_id = data.get('testId', '')
        print(f"[CMD] Run test: {test_id}")
        # Run test in background task
        asyncio.create_task(_run_test(ws, test_id))

    elif cmd_type == 'run_all_tests':
        print(f"[CMD] Run all tests")
        asyncio.create_task(_run_all_tests(ws))

    elif cmd_type == 'generate_report':
        print(f"[CMD] Generate FAT report")
        asyncio.create_task(_generate_report(ws))

    else:
        print(f"[CMD] Unknown command: {cmd_type}")


async def _run_test(ws, test_id):
    """Execute a single test and stream results."""
    async def progress_cb(tid, pct):
        await broadcast_message('test_progress', {
            'testId': tid, 'progress': pct,
        })
        await asyncio.sleep(0)  # yield to event loop

    tc = await test_engine.run_single(test_id, progress_cb)
    if tc:
        await broadcast_message('test_result', {
            'testId': test_id,
            'result': tc.to_dict(),
        })
        print(f"[TEST] {test_id} — {tc.status.upper()}")


async def _run_all_tests(ws):
    """Execute all tests sequentially and stream results."""
    async def progress_cb(tid, pct, overall):
        await broadcast_message('test_progress', {
            'testId': tid, 'progress': pct, 'overall': overall,
        })
        await asyncio.sleep(0)

    results = await test_engine.run_all(progress_cb)
    summary = test_engine.get_summary()

    await broadcast_message('test_complete', {
        'summary': summary,
    })
    print(f"[TEST] All tests complete — {summary['passed']}/{summary['total']} passed")


async def _generate_report(ws):
    """Generate PDF report and notify client."""
    summary = test_engine.get_summary()
    if summary['total'] == 0:
        await broadcast_message('report_error', {
            'error': 'No test results available. Run tests first.',
        })
        return

    output_path = os.path.join(os.path.dirname(__file__), '..', 'FAT_Report.pdf')
    path = generate_fat_report(summary, output_path)

    if path:
        await broadcast_message('report_ready', {
            'path': os.path.abspath(path),
        })
    else:
        await broadcast_message('report_error', {
            'error': 'Failed to generate report. Check reportlab installation.',
        })


async def handle_client(websocket):
    """Handle a single WebSocket client connection."""
    connected_clients.add(websocket)
    client_addr = websocket.remote_address
    print(f"[WS] Client connected: {client_addr}")

    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                await handle_command(websocket, data)
            except json.JSONDecodeError:
                print(f"[WS] Invalid JSON from {client_addr}")
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        connected_clients.discard(websocket)
        print(f"[WS] Client disconnected: {client_addr}")


async def main():
    """Start the DRIVEWISE simulation backend."""
    host = "0.0.0.0"
    port = 8765

    print("=" * 60)
    print("  DRIVEWISE — Simulation Backend")
    print("  Multi-Drive Industrial Simulation Engine")
    print("=" * 60)
    print(f"  WebSocket server: ws://{host}:{port}")
    print(f"  Simulation dt:    {coordinator.dt}s")
    print(f"  Speed multiplier: {coordinator.speed_multiplier}x")
    print(f"  Drive units:      S1, S2, S3")
    print(f"  Test cases:       6 FAT tests")
    print("=" * 60)
    print()

    # Start WebSocket server
    server = await websockets.serve(
        handle_client,
        host,
        port,
        ping_interval=20,
        ping_timeout=20,
    )

    print(f"[OK] WebSocket server listening on ws://{host}:{port}")
    print("[OK] Simulation engine running. Waiting for connections...")
    print()

    # Start broadcast loop
    broadcast_task = asyncio.create_task(broadcast_tags())

    # Keep running
    await asyncio.gather(server.wait_closed(), broadcast_task)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[SHUTDOWN] DRIVEWISE backend stopped.")
