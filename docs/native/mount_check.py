import subprocess

result = subprocess.run(
    ["findmnt", "-n", "-o", "UUID", "-T", "/mnt/house-storage"], capture_output=True, text=True, timeout=5
)
if result.returncode or result.stdout.strip() != "SET_YOUR_STORAGE_UUID":
    raise SystemExit("HouseOS expected storage filesystem is absent")
