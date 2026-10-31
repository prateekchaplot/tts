"""Device detection helpers."""

import re


def _normalize_requested(requested):
    requested = (requested or "auto").lower().strip()
    if requested == "auto":
        return "auto"
    if requested == "cpu":
        return "cpu"
    m = re.fullmatch(r"cuda(?::(\d+))?", requested)
    if m:
        idx = m.group(1)
        return "cuda" if idx is None else f"cuda:{idx}"
    return requested


def detect_device(requested="auto", verbose=False):
    requested = _normalize_requested(requested)
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
    elif requested == "cpu":
        dev = "cpu"
    elif requested.startswith("cuda"):
        if not torch.cuda.is_available():
            print(f"[device] requested={requested} but CUDA is not available; falling back to cpu")
            dev = "cpu"
        else:
            dev = requested
    else:
        print(f"[device] unknown device '{requested}'; falling back to cpu")
        dev = "cpu"
    print(f"[device] requested={requested} -> {dev}")
    if dev.startswith("cuda"):
        try:
            idx = _device_index(dev)
            name = torch.cuda.get_device_name(idx if idx >= 0 else 0)
            vram = torch.cuda.get_device_properties(idx if idx >= 0 else 0).total_memory / (1024 ** 3)
            print(f"[device] GPU: {name} ({vram:.1f} GB VRAM)")
        except Exception as e:
            print(f"[device] GPU info unavailable: {e}")
    else:
        print("[device] running on CPU")
    return dev


def _device_index(device):
    if not device:
        return -1
    device = str(device).lower().strip()
    if device == "cpu":
        return -1
    m = re.fullmatch(r"cuda(?::(\d+))?", device)
    if not m:
        return -1
    idx = m.group(1)
    return 0 if idx is None else int(idx)


def torch_device_name(device):
    """Return a torch-compatible device string (e.g. 'cuda:0' or 'cpu')."""
    idx = _device_index(device)
    if idx >= 0:
        return f"cuda:{idx}" if idx > 0 else "cuda"
    return "cpu"