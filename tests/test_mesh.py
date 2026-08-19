from boddos.mesh.node import NodeInfo, MeshRegistry
from boddos.mesh.router import Router


def make_registry():
    me = NodeInfo(id="hp", name="HP", role="edge", url="http://hp:8787", ram_gb=8)
    reg = MeshRegistry(me, ttl=30)
    reg.from_hello({"id": "macbook", "role": "host", "url": "http://mac:8787",
                    "ram_gb": 32, "has_gpu": True, "models": ["llama3.1"]})
    reg.from_hello({"id": "zbook", "role": "host", "url": "http://zb:8787",
                    "ram_gb": 32, "has_gpu": False, "models": ["llama3.1"]})
    return reg


def test_registry_ignores_self():
    reg = make_registry()
    reg.from_hello({"id": "hp", "role": "edge", "url": "x"})
    assert {p.id for p in reg.alive_peers()} == {"macbook", "zbook"}


def test_router_prefers_local_when_capable():
    reg = make_registry()
    r = Router(reg)
    assert r.select_model_node("llama3.1", local_models=["llama3.1"]).id == "hp"


def test_router_picks_gpu_host_peer():
    reg = make_registry()
    r = Router(reg)
    # HP can't serve it locally; both hosts have it, GPU host wins.
    assert r.select_model_node("llama3.1", local_models=[]).id == "macbook"


def test_router_falls_back_to_any_host():
    reg = make_registry()
    r = Router(reg)
    chosen = r.select_model_node("some-other-model", local_models=[])
    assert chosen.id in {"macbook", "zbook"}
