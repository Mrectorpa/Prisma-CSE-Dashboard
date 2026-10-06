import importlib.util
spec = importlib.util.spec_from_file_location("m", "RN-SPN-NAME-N-IP.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

print("=== Testing get_public_ips() in isolation ===")
ips = m.get_public_ips()
print(f"Result count: {len(ips)}")
print(f"Sample: {ips[:5]}")
