"""The firewall file has to match the address plan before it is loaded on Linux."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_firewall_matches_address_plan() -> None:
    addresses = (ROOT / "network" / "addresses.env").read_text(encoding="utf-8")
    firewall = (ROOT / "network" / "firewall.nft").read_text(encoding="utf-8")
    assert "FT_CLIENT_NET=10.10.10.0/24" in addresses
    assert "FT_SERVICE_IP=10.20.20.10" in addresses
    assert "FT_DATA_IP=10.30.30.10" in addresses
    assert "policy drop" in firewall
    assert "tcp dport 8443" in firewall
    assert "tcp dport 27017" in firewall
    assert "10.10.10.0/24" in firewall
    assert "10.20.20.10" in firewall
    assert "10.30.30.10" in firewall
    for line in firewall.splitlines():
        if "accept" in line and "27017" in line:
            assert "10.20.20.10" in line
            assert "10.10.10" not in line


def test_mongod_is_bound_to_the_data_address_without_a_unix_socket() -> None:
    config = (ROOT / "network" / "mongod.conf").read_text(encoding="utf-8")
    assert "bindIp: 10.30.30.10" in config
    assert "enabled: false" in config
    assert "27017" in config
