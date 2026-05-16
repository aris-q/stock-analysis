import json, math

with open("output/dream.json", "r") as f:
    raw = f.read()

# Python can parse its own NaN output
data = eval(raw, {"NaN": float("nan"), "Infinity": float("inf"), "true": True, "false": False, "null": None})

def sanitize(obj):
    if isinstance(obj, dict):
        return {k: sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize(v) for v in obj]
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    return obj

with open("output/dream.json", "w") as f:
    json.dump(sanitize(data), f, indent=2)

print("Done")


