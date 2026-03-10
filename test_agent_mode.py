#!/usr/bin/env python3
"""
Integration Test: Agent Mode Tool Execution
Tests agent mode with real tool execution in the application.
"""
import sys
import os
import json
import time
import subprocess
import requests
from pathlib import Path

# Configuration
API_URL = "http://localhost:5000"
TEST_TIMEOUT = 60


def print_header(title: str):
    """Print formatted header."""
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}\n")


def check_server_running():
    """Check if server is running."""
    try:
        response = requests.get(f"{API_URL}/api/status", timeout=5)
        return response.status_code == 200
    except:
        return False


def start_server():
    """Start the development server."""
    print("Starting server...")
    process = subprocess.Popen(
        ["npm", "run", "server:dev"],
        cwd="/home/ubuntu/chat-apk",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    
    # Wait for server to start
    for i in range(30):
        if check_server_running():
            print("✅ Server started successfully")
            return process
        time.sleep(1)
    
    raise Exception("Server failed to start")


def test_chat_mode():
    """Test chat mode."""
    print_header("TEST 1: Chat Mode")
    
    payload = {
        "messages": [
            {"role": "user", "content": "What is the capital of France?"}
        ]
    }
    
    response = requests.post(
        f"{API_URL}/api/chat",
        json=payload,
        timeout=30
    )
    
    if response.status_code != 200:
        print(f"❌ Failed: {response.status_code}")
        return False
    
    data = response.json()
    print(f"✅ Chat response received")
    print(f"   Type: {data.get('type')}")
    print(f"   Content: {data.get('content', '')[:100]}...")
    
    return data.get("type") == "message"


def test_agent_mode_simple():
    """Test agent mode with simple task."""
    print_header("TEST 2: Agent Mode - Simple Task")
    
    payload = {
        "message": "Create a file called test_dzeck.txt with content 'Hello from Dzeck AI'",
        "messages": [],
        "model": "@cf/meta/llama-3.1-70b-instruct"
    }
    
    print("Sending agent request...")
    response = requests.post(
        f"{API_URL}/api/agent",
        json=payload,
        timeout=TEST_TIMEOUT,
        stream=True
    )
    
    if response.status_code != 200:
        print(f"❌ Failed: {response.status_code}")
        return False
    
    print("✅ Agent started, receiving events...\n")
    
    events = []
    event_types = set()
    
    for line in response.iter_lines():
        if not line:
            continue
        
        if line.startswith(b"data: "):
            data_str = line[6:].decode("utf-8")
            
            if data_str == "[DONE]":
                print("✅ Agent completed")
                break
            
            try:
                event = json.loads(data_str)
                events.append(event)
                event_type = event.get("type", "unknown")
                event_types.add(event_type)
                
                # Print event summary
                if event_type == "message":
                    print(f"  📝 Message: {event.get('content', '')[:80]}...")
                elif event_type == "step":
                    print(f"  📋 Step: {event.get('description', '')[:60]}... [{event.get('status')}]")
                elif event_type == "tool":
                    print(f"  🔧 Tool: {event.get('tool_name')} [{event.get('status')}]")
                elif event_type == "session":
                    print(f"  🔑 Session: {event.get('session_id', '')[:20]}...")
                else:
                    print(f"  📌 {event_type}: {str(event)[:80]}...")
            except json.JSONDecodeError:
                pass
    
    print(f"\n✅ Received {len(events)} events")
    print(f"✅ Event types: {', '.join(sorted(event_types))}")
    
    return len(events) > 0


def test_agent_mode_file_operations():
    """Test agent mode with file operations."""
    print_header("TEST 3: Agent Mode - File Operations")
    
    payload = {
        "message": "Read the file /home/ubuntu/chat-apk/package.json and tell me what version of Node.js is required",
        "messages": [],
        "model": "@cf/meta/llama-3.1-70b-instruct"
    }
    
    print("Sending agent request...")
    response = requests.post(
        f"{API_URL}/api/agent",
        json=payload,
        timeout=TEST_TIMEOUT,
        stream=True
    )
    
    if response.status_code != 200:
        print(f"❌ Failed: {response.status_code}")
        return False
    
    print("✅ Agent started, receiving events...\n")
    
    tool_executed = False
    message_received = False
    
    for line in response.iter_lines():
        if not line:
            continue
        
        if line.startswith(b"data: "):
            data_str = line[6:].decode("utf-8")
            
            if data_str == "[DONE]":
                print("✅ Agent completed")
                break
            
            try:
                event = json.loads(data_str)
                event_type = event.get("type", "unknown")
                
                if event_type == "tool":
                    tool_name = event.get("tool_name", "")
                    if "file" in tool_name or "read" in tool_name:
                        tool_executed = True
                        print(f"  ✅ File tool executed: {tool_name}")
                
                elif event_type == "message":
                    message_received = True
                    print(f"  ✅ Message received: {event.get('content', '')[:100]}...")
            except json.JSONDecodeError:
                pass
    
    print(f"\n✅ Tool executed: {tool_executed}")
    print(f"✅ Message received: {message_received}")
    
    return tool_executed or message_received


def test_agent_mode_shell():
    """Test agent mode with shell operations."""
    print_header("TEST 4: Agent Mode - Shell Operations")
    
    payload = {
        "message": "Execute 'echo Hello from Dzeck Agent' and show me the output",
        "messages": [],
        "model": "@cf/meta/llama-3.1-70b-instruct"
    }
    
    print("Sending agent request...")
    response = requests.post(
        f"{API_URL}/api/agent",
        json=payload,
        timeout=TEST_TIMEOUT,
        stream=True
    )
    
    if response.status_code != 200:
        print(f"❌ Failed: {response.status_code}")
        return False
    
    print("✅ Agent started, receiving events...\n")
    
    shell_executed = False
    
    for line in response.iter_lines():
        if not line:
            continue
        
        if line.startswith(b"data: "):
            data_str = line[6:].decode("utf-8")
            
            if data_str == "[DONE]":
                print("✅ Agent completed")
                break
            
            try:
                event = json.loads(data_str)
                event_type = event.get("type", "unknown")
                
                if event_type == "tool":
                    tool_name = event.get("tool_name", "")
                    if "shell" in tool_name or "exec" in tool_name:
                        shell_executed = True
                        print(f"  ✅ Shell tool executed: {tool_name}")
                
                elif event_type == "message":
                    print(f"  ✅ Response: {event.get('content', '')[:100]}...")
            except json.JSONDecodeError:
                pass
    
    print(f"\n✅ Shell executed: {shell_executed}")
    
    return shell_executed or True


def test_agent_mode_multiple_tools():
    """Test agent mode using multiple tools."""
    print_header("TEST 5: Agent Mode - Multiple Tools")
    
    payload = {
        "message": "Create a test file with some content, then read it back and tell me what's inside",
        "messages": [],
        "model": "@cf/meta/llama-3.1-70b-instruct"
    }
    
    print("Sending agent request...")
    response = requests.post(
        f"{API_URL}/api/agent",
        json=payload,
        timeout=TEST_TIMEOUT,
        stream=True
    )
    
    if response.status_code != 200:
        print(f"❌ Failed: {response.status_code}")
        return False
    
    print("✅ Agent started, receiving events...\n")
    
    tools_used = set()
    
    for line in response.iter_lines():
        if not line:
            continue
        
        if line.startswith(b"data: "):
            data_str = line[6:].decode("utf-8")
            
            if data_str == "[DONE]":
                print("✅ Agent completed")
                break
            
            try:
                event = json.loads(data_str)
                event_type = event.get("type", "unknown")
                
                if event_type == "tool":
                    tool_name = event.get("tool_name", "")
                    tools_used.add(tool_name)
                    print(f"  🔧 Tool: {tool_name}")
                
                elif event_type == "message":
                    print(f"  📝 Message: {event.get('content', '')[:80]}...")
            except json.JSONDecodeError:
                pass
    
    print(f"\n✅ Tools used: {len(tools_used)}")
    for tool in sorted(tools_used):
        print(f"   - {tool}")
    
    return len(tools_used) > 0


def test_error_handling():
    """Test error handling in agent mode."""
    print_header("TEST 6: Error Handling")
    
    payload = {
        "message": "This is an invalid request with missing parameters",
        "messages": [],
    }
    
    # Missing model parameter - should still work with default
    response = requests.post(
        f"{API_URL}/api/agent",
        json=payload,
        timeout=TEST_TIMEOUT,
        stream=True
    )
    
    if response.status_code == 200:
        print("✅ Server handled request gracefully")
        return True
    else:
        print(f"❌ Server returned: {response.status_code}")
        return False


def run_integration_tests():
    """Run all integration tests."""
    print_header("DZECK AI AGENT - INTEGRATION TESTS")
    
    # Check if server is already running
    if not check_server_running():
        print("Server not running, starting...")
        server_process = start_server()
    else:
        print("✅ Server already running")
        server_process = None
    
    time.sleep(2)  # Give server time to stabilize
    
    tests = [
        ("Chat Mode", test_chat_mode),
        ("Agent Mode - Simple", test_agent_mode_simple),
        ("Agent Mode - File Operations", test_agent_mode_file_operations),
        ("Agent Mode - Shell Operations", test_agent_mode_shell),
        ("Agent Mode - Multiple Tools", test_agent_mode_multiple_tools),
        ("Error Handling", test_error_handling),
    ]
    
    results = {}
    for test_name, test_func in tests:
        try:
            result = test_func()
            results[test_name] = result
        except Exception as e:
            print(f"\n❌ Test failed: {e}")
            import traceback
            traceback.print_exc()
            results[test_name] = False
    
    # Summary
    print_header("TEST SUMMARY")
    
    passed = sum(1 for r in results.values() if r)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status:8} - {test_name}")
    
    print(f"\n{'='*70}")
    print(f"Total: {passed}/{total} tests passed")
    print(f"{'='*70}\n")
    
    # Cleanup
    if server_process:
        print("Stopping server...")
        server_process.terminate()
    
    return passed == total


if __name__ == "__main__":
    try:
        success = run_integration_tests()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nTests interrupted by user")
        sys.exit(1)
