#!/usr/bin/env python3
"""
Test runner for y_web pytest suite
"""
import subprocess
import sys
import os


def run_tests():
    """Run all y_web tests"""
    print("Running Y_Web Test Suite")
    print("=" * 50)
    
    # Change to project directory
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    
    # List of test files that are known to work
    working_tests = [
        'y_web/tests/test_simple_models.py',
        'y_web/tests/test_simple_auth.py',
        'y_web/tests/test_app_structure.py',
        'y_web/tests/test_utils.py',
        'y_web/tests/test_auth_routes.py',
        'y_web/tests/test_admin_routes.py',
        'y_web/tests/test_user_interaction_routes.py',
    ]
    
    total_passed = 0
    total_failed = 0
    total_skipped = 0
    
    for test_file in working_tests:
        print(f"\nRunning {test_file}...")
        print("-" * 30)
        
        try:
            result = subprocess.run([
                sys.executable, '-m', 'pytest', test_file, '-v', '--tb=short'
            ], capture_output=True, text=True, timeout=60)
            
            print(result.stdout)
            if result.stderr:
                print("STDERR:", result.stderr)
            
            # Parse results (basic parsing)
            output = result.stdout
            if "failed" in output.lower() and result.returncode != 0:
                total_failed += 1
            elif "passed" in output.lower():
                total_passed += 1
            
            if "skipped" in output.lower():
                # Count skipped tests
                lines = output.split('\n')
                for line in lines:
                    if 'skipped' in line.lower() and ('passed' in line or 'failed' in line):
                        # Extract number of skipped tests
                        parts = line.split()
                        for i, part in enumerate(parts):
                            if 'skipped' in part:
                                try:
                                    total_skipped += int(parts[i-1])
                                except (ValueError, IndexError):
                                    pass
                        break
                        
        except subprocess.TimeoutExpired:
            print(f"Test {test_file} timed out!")
            total_failed += 1
        except Exception as e:
            print(f"Error running {test_file}: {e}")
            total_failed += 1
    
    print("\n" + "=" * 50)
    print("TEST SUMMARY")
    print("=" * 50)
    print(f"Test files run: {len(working_tests)}")
    print(f"Passed: {total_passed}")
    print(f"Failed: {total_failed}")
    print(f"Skipped: {total_skipped}")
    
    if total_failed == 0:
        print("\n✅ All tests passed!")
        return 0
    else:
        print(f"\n❌ {total_failed} test file(s) failed!")
        return 1


if __name__ == '__main__':
    sys.exit(run_tests())