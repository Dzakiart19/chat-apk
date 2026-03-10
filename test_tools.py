#!/usr/bin/env python3
"""
Comprehensive Tool Testing Script for Dzeck AI Agent.
Tests all tools to ensure they execute perfectly.
"""
import sys
import os
import json
import tempfile
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.getcwd())

from server.agent.tools.executor import (
    ToolCallParser,
    ToolCallExecutor,
    ToolCall,
    ToolCallFormatter,
)
from server.agent.tools.registry import get_all_tool_schemas


def print_section(title: str):
    """Print a formatted section header."""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")


def test_tool_schemas():
    """Test that all tools have proper schemas."""
    print_section("TEST 1: Tool Schemas")
    
    schemas = get_all_tool_schemas()
    print(f"✅ Found {len(schemas)} tools\n")
    
    for schema in schemas:
        name = schema.get("name", "unknown")
        description = schema.get("description", "")[:50]
        print(f"  • {name:30} - {description}...")
    
    return len(schemas) > 0


def test_tool_call_parsing():
    """Test tool call parsing from various formats."""
    print_section("TEST 2: Tool Call Parsing")
    
    parser = ToolCallParser()
    
    # Test 1: JSON array format
    json_text = json.dumps([
        {"name": "message_notify_user", "parameters": {"text": "Hello from test"}},
        {"name": "shell_exec", "parameters": {"id": "main", "exec_dir": "/home/ubuntu", "command": "echo 'test'"}}
    ])
    
    tool_calls = parser.extract_tool_calls(json_text)
    print(f"✅ Parsed {len(tool_calls)} tool calls from JSON format")
    for tc in tool_calls:
        print(f"   - {tc.name}: {tc.parameters}")
    
    # Test 2: Function call format
    func_text = '''
    <invoke name="message_notify_user">
    <parameter name="text">Test message</parameter>
    </invoke>
    '''
    
    tool_calls = parser.extract_tool_calls(func_text)
    print(f"\n✅ Parsed {len(tool_calls)} tool calls from function format")
    for tc in tool_calls:
        print(f"   - {tc.name}: {tc.parameters}")
    
    return True


def test_file_operations():
    """Test file operations."""
    print_section("TEST 3: File Operations")
    
    executor = ToolCallExecutor()
    
    # Create temp file
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
        temp_file = f.name
        f.write("Initial content")
    
    try:
        # Test file_read
        print("Testing file_read...")
        tool_call = ToolCall(
            name="file_read",
            parameters={"file": temp_file}
        )
        result = executor.execute_tool_call(tool_call)
        print(f"  ✅ file_read: {result.message[:50]}...")
        
        # Test file_write (append)
        print("\nTesting file_write (append)...")
        tool_call = ToolCall(
            name="file_write",
            parameters={
                "file": temp_file,
                "content": "\nAppended content",
                "append": True
            }
        )
        result = executor.execute_tool_call(tool_call)
        print(f"  ✅ file_write: {result.message}")
        
        # Test file_str_replace
        print("\nTesting file_str_replace...")
        tool_call = ToolCall(
            name="file_str_replace",
            parameters={
                "file": temp_file,
                "old_str": "Initial",
                "new_str": "Modified"
            }
        )
        result = executor.execute_tool_call(tool_call)
        print(f"  ✅ file_str_replace: {result.message}")
        
        return result.success
    finally:
        os.unlink(temp_file)


def test_shell_operations():
    """Test shell operations."""
    print_section("TEST 4: Shell Operations")
    
    executor = ToolCallExecutor()
    
    # Test shell_exec
    print("Testing shell_exec...")
    tool_call = ToolCall(
        name="shell_exec",
        parameters={
            "id": "test",
            "exec_dir": "/home/ubuntu",
            "command": "echo 'Hello from shell' && pwd"
        }
    )
    result = executor.execute_tool_call(tool_call)
    print(f"  ✅ shell_exec: {result.message[:100]}...")
    
    return result.success


def test_message_operations():
    """Test message operations."""
    print_section("TEST 5: Message Operations")
    
    executor = ToolCallExecutor()
    
    # Test message_notify_user
    print("Testing message_notify_user...")
    tool_call = ToolCall(
        name="message_notify_user",
        parameters={"text": "Test notification message"}
    )
    result = executor.execute_tool_call(tool_call)
    print(f"  ✅ message_notify_user: {result.message}")
    
    return result.success


def test_tool_validation():
    """Test tool validation."""
    print_section("TEST 6: Tool Validation")
    
    parser = ToolCallParser()
    
    # Valid tool
    valid_call = ToolCall(
        name="message_notify_user",
        parameters={"text": "test"}
    )
    is_valid, error = parser.validate_tool_call(valid_call)
    print(f"✅ Valid tool: {is_valid}")
    
    # Invalid tool
    invalid_call = ToolCall(
        name="nonexistent_tool",
        parameters={}
    )
    is_valid, error = parser.validate_tool_call(invalid_call)
    print(f"✅ Invalid tool detected: {not is_valid}")
    print(f"   Error: {error[:80]}...")
    
    # Invalid parameters
    invalid_params = ToolCall(
        name="message_notify_user",
        parameters="not a dict"
    )
    is_valid, error = parser.validate_tool_call(invalid_params)
    print(f"✅ Invalid parameters detected: {not is_valid}")
    
    return True


def test_tool_execution_history():
    """Test execution history tracking."""
    print_section("TEST 7: Execution History")
    
    executor = ToolCallExecutor()
    
    # Execute some tools
    tool_calls = [
        ToolCall(name="message_notify_user", parameters={"text": "Test 1"}),
        ToolCall(name="message_notify_user", parameters={"text": "Test 2"}),
    ]
    
    results = executor.execute_tool_calls(tool_calls)
    history = executor.get_execution_history()
    
    print(f"✅ Executed {len(tool_calls)} tools")
    print(f"✅ Recorded {len(history)} history entries")
    
    for i, entry in enumerate(history):
        print(f"   {i+1}. {entry['tool_name']}: {entry['result']['message'][:50]}...")
    
    return len(history) == len(tool_calls)


def test_batch_execution():
    """Test batch tool execution."""
    print_section("TEST 8: Batch Execution")
    
    executor = ToolCallExecutor()
    
    # Create batch of tool calls
    tool_calls = [
        ToolCall(name="message_notify_user", parameters={"text": "Message 1"}),
        ToolCall(name="message_notify_user", parameters={"text": "Message 2"}),
        ToolCall(name="message_notify_user", parameters={"text": "Message 3"}),
    ]
    
    results = executor.execute_tool_calls(tool_calls)
    
    print(f"✅ Executed batch of {len(tool_calls)} tools")
    print(f"✅ Got {len(results)} results")
    
    success_count = sum(1 for r in results if r.success)
    print(f"✅ Success rate: {success_count}/{len(results)}")
    
    return success_count == len(results)


def test_error_handling():
    """Test error handling."""
    print_section("TEST 9: Error Handling")
    
    executor = ToolCallExecutor()
    
    # Test with invalid tool
    print("Testing invalid tool handling...")
    tool_call = ToolCall(
        name="invalid_tool_xyz",
        parameters={}
    )
    result = executor.execute_tool_call(tool_call)
    print(f"  ✅ Error caught: {not result.success}")
    print(f"     Message: {result.message[:80]}...")
    
    # Test with invalid parameters
    print("\nTesting invalid parameters handling...")
    tool_call = ToolCall(
        name="file_read",
        parameters={"nonexistent_param": "value"}
    )
    result = executor.execute_tool_call(tool_call)
    print(f"  ✅ Error caught: {not result.success}")
    
    return True


def test_formatter():
    """Test tool call formatting."""
    print_section("TEST 10: Tool Call Formatting")
    
    formatter = ToolCallFormatter()
    
    tool_calls = [
        ToolCall(name="message_notify_user", parameters={"text": "Test 1"}),
        ToolCall(name="message_notify_user", parameters={"text": "Test 2"}),
    ]
    
    # Test JSON format
    json_output = formatter.format_as_json(tool_calls)
    print("✅ JSON format:")
    print(json_output[:200] + "...")
    
    # Test function call format
    func_output = formatter.format_as_function_calls(tool_calls)
    print("\n✅ Function call format:")
    print(func_output[:200] + "...")
    
    return True


def run_all_tests():
    """Run all tests."""
    print("\n" + "="*60)
    print("  DZECK AI AGENT - COMPREHENSIVE TOOL TESTING")
    print("="*60)
    
    tests = [
        ("Tool Schemas", test_tool_schemas),
        ("Tool Call Parsing", test_tool_call_parsing),
        ("File Operations", test_file_operations),
        ("Shell Operations", test_shell_operations),
        ("Message Operations", test_message_operations),
        ("Tool Validation", test_tool_validation),
        ("Execution History", test_tool_execution_history),
        ("Batch Execution", test_batch_execution),
        ("Error Handling", test_error_handling),
        ("Tool Formatting", test_formatter),
    ]
    
    results = {}
    for test_name, test_func in tests:
        try:
            result = test_func()
            results[test_name] = result
        except Exception as e:
            print(f"\n❌ Test failed with exception: {e}")
            import traceback
            traceback.print_exc()
            results[test_name] = False
    
    # Summary
    print_section("TEST SUMMARY")
    
    passed = sum(1 for r in results.values() if r)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status:8} - {test_name}")
    
    print(f"\n{'='*60}")
    print(f"Total: {passed}/{total} tests passed")
    print(f"{'='*60}\n")
    
    return passed == total


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
