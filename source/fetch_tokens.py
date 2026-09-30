#!/usr/bin/env python3
"""Snapshot minted Swarm Pepe SVGs directly from Ethereum mainnet."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
RPC = "https://ethereum-rpc.publicnode.com"
SWARM = "0x999ce0ce8c5f7661e0c74a568ffe27ceb9177bdb"
PIXEL_ART = "0x07Fd9841eEB6a359EfB30f861D59bFa1f6B03FcA"


def rpc(method, params):
    data = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    response = subprocess.run(["curl", "-fsS", "--max-time", "45", "-H",
                               "Content-Type: application/json", "--data-binary", "@-", RPC],
                              input=data, capture_output=True, check=True)
    result = json.loads(response.stdout)
    if "error" in result:
        raise RuntimeError(result["error"])
    return result["result"]


def call(contract, selector, argument, block):
    data = "0x" + selector + (f"{argument:064x}" if argument is not None else "")
    return bytes.fromhex(rpc("eth_call", [{"to": contract, "data": data}, block])[2:])


def abi_string(data):
    start = int.from_bytes(data[:32], "big")
    length = int.from_bytes(data[start:start + 32], "big")
    return data[start + 32:start + 32 + length].decode("utf-8")


def main(ids):
    block = rpc("eth_blockNumber", [])
    block_info = rpc("eth_getBlockByNumber", [block, False])
    supply = int.from_bytes(call(SWARM, "a2309ff8", None, block), "big")
    max_supply = int.from_bytes(call(SWARM, "32cb6b0c", None, block), "big")
    # MAX_SUPPLY selector is verified against the known 5,000 cap below.
    if max_supply != 5000:
        raise RuntimeError(f"Unexpected max supply: {max_supply}")
    out = ROOT / "assets"
    out.mkdir(exist_ok=True)
    tokens = []
    for token_id in ids:
        if not 1 <= token_id <= supply:
            raise ValueError(f"Token #{token_id} is outside the minted range")
        call(SWARM, "6352211e", token_id, block)  # ownerOf: existence only
        seed = int.from_bytes(call(SWARM, "82829f74", token_id, block), "big")
        if seed == 0:
            raise RuntimeError(f"Token #{token_id} has not revealed")
        svg = abi_string(call(PIXEL_ART, "d12a4c98", seed, block))
        if not svg.startswith("<svg") or 'viewBox="0 0 24 24"' not in svg:
            raise RuntimeError(f"Unexpected SVG returned for token #{token_id}")
        name = f"token_{token_id:04d}.svg"
        (out / name).write_text(svg)
        tokens.append({"id": token_id, "seed": str(seed), "svg": name,
                       "sha256": hashlib.sha256(svg.encode()).hexdigest()})
        print(f"#{token_id}: {name} ({len(svg)} bytes)", flush=True)
    provenance = {"chain": "Ethereum mainnet", "block": block,
                  "block_decimal": int(block, 16),
                  "block_utc": datetime.fromtimestamp(int(block_info["timestamp"], 16), timezone.utc).isoformat(),
                  "total_minted": supply,
                  "max_supply": max_supply, "swarm_pepe": SWARM,
                  "pixel_art": PIXEL_ART,
                  "calls": ["totalMinted()", "MAX_SUPPLY()", "ownerOf(id)",
                            "seedOf(id)", "renderSVG(seed)"],
                  "tokens": tokens}
    (out / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    print(f"Minted: {supply}/{max_supply} at block {provenance['block_decimal']}")


if __name__ == "__main__":
    main([int(arg) for arg in sys.argv[1:]] or list(range(1, 13)))
