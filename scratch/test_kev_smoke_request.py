import time
import json
import urllib.request
import psutil

# Find Kev server process
pid = 48692
try:
    proc = psutil.Process(pid)
    ram_before_mb = proc.memory_info().rss / (1024 * 1024)
except Exception:
    proc = None
    ram_before_mb = None

payload = {
    "model": "kev-latest",
    "state": "Revenue increased from R100 million to R120 million.",
    "questions": {
        "financial_metric": {
            "type": "choice",
            "criteria": {
                "revenue": "Sales, turnover, or top-line business revenue",
                "profit": "Earnings, net income, or bottom-line profit",
                "cash_flow": "Cash generated from operations or liquidity"
            }
        },
        "direction": {
            "type": "choice",
            "criteria": {
                "increase": "The figure grew, increased, or moved higher",
                "decrease": "The figure fell, decreased, or moved lower",
                "flat": "The figure remained flat or unchanged"
            }
        }
    }
}

req_data = json.dumps(payload).encode("utf-8")
req = urllib.request.Request(
    "http://127.0.0.1:8009/v1/systemone",
    data=req_data,
    headers={"Content-Type": "application/json"}
)

t0 = time.perf_counter()
with urllib.request.urlopen(req) as resp:
    res_bytes = resp.read()
    status_code = resp.status
t1 = time.perf_counter()

client_elapsed_ms = (t1 - t0) * 1000

if proc:
    ram_after_mb = proc.memory_info().rss / (1024 * 1024)
else:
    ram_after_mb = None

res_json = json.loads(res_bytes.decode("utf-8"))

output = {
    "status_code": status_code,
    "client_elapsed_ms": client_elapsed_ms,
    "ram_before_mb": ram_before_mb,
    "ram_after_mb": ram_after_mb,
    "response": res_json
}

print(json.dumps(output, indent=2))
