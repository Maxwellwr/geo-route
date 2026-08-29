import pytest
from bindaddr import iface_ipv4, lan_ipv4

BR0 = "2: br0    inet 192.168.117.1/24 brd 192.168.117.255 scope global br0\n"
WAN = "3: eth3    inet 100.64.1.2/24 scope global eth3\n"
WG = "4: nwg0    inet 10.7.0.2/24 scope global nwg0\n"

def test_prefers_br0():
    assert lan_ipv4(WAN + WG + BR0, "default via 100.64.1.1 dev eth3") == "192.168.117.1"

def test_error_if_only_wan_and_wg():
    with pytest.raises(RuntimeError):
        lan_ipv4(WAN + WG, "default via 100.64.1.1 dev eth3")

def test_fallback_private_not_wan():
    lan = "5: br1    inet 192.168.1.1/24 scope global br1\n"
    assert lan_ipv4(WAN + lan, "default via 100.64.1.1 dev eth3") == "192.168.1.1"


def test_iface_ipv4_returns_requested_interface():
    assert iface_ipv4(WAN + WG + BR0, "nwg0") == "10.7.0.2"


def test_iface_ipv4_does_not_fall_back_to_other_private_address():
    with pytest.raises(RuntimeError):
        iface_ipv4(BR0, "nwg0")
