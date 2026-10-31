"""Device detection helpers."""


def detect_device(requested="auto", verbose=False):
    requested = (requested or "auto").lower()
    try:
        import torch
    except Exception as e:
        print(f"[device] torch not available ({e}); forcing cpu")
        return "cpu"
    if requested == "auto":
        if torch.cuda.is_available():
            dev = "cuda"
        else:
            dev = "cpu"
    else:
        dev = requested
    print(f"[device] requested={requested} -> {dev}")
    if dev == "cuda":
        try:
            name = torch.cuda.get_device_name(0)
            vram = torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)
            print(f"[device] GPU: {name} ({vram:.1f} GB VRAM)")
        except Exception as e:
            print(f"[device] GPU info unavailable: {e}")
    else:
        print("[device] running on CPU")
    return dev


def _device_index(device):
    if device == "cuda":
        return 0
    return -1
