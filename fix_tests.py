import os
from pathlib import Path

tests_dir = Path("y_web/tests")
for test_file in tests_dir.glob("*.py"):
    with open(test_file, "r") as f:
        content = f.read()
    if "/Users/rossetti/PycharmProjects/YWeb/" in content:
        content = content.replace("/Users/rossetti/PycharmProjects/YWeb/", "/app/")
        with open(test_file, "w") as f:
            f.write(content)

print("Fixed tests hardcoded paths")
