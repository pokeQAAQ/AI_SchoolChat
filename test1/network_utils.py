import os
import subprocess

def get_network_interfaces():
    """Return a list of network interfaces."""
    interfaces = []
    for interface in os.listdir('/sys/class/net/'):
        interfaces.append(interface)
    return interfaces

def get_mac_address(interface):
    """Return the MAC address of a given interface."""
    try:
        # Method 1: Read from sysfs
        with open(f'/sys/class/net/{interface}/address') as f:
            return f.read().strip()
    except FileNotFoundError:
        pass
    
    try:
        # Method 2: Use ifconfig command
        output = subprocess.check_output(['ifconfig', interface]).decode()
        for line in output.split('\n'):
            if 'ether' in line:
                return line.split()[1]
    except Exception:
        pass
    
    try:
        # Method 3: Use ip command
        output = subprocess.check_output(['ip', 'link', 'show', interface]).decode()
        for line in output.split('\n'):
            if 'link/ether' in line:
                return line.split()[1]
    except Exception:
        pass
    
    return None  # Fallback if no MAC address could be found
def get_ip_address(interface):
    """Return the IP address of a given interface."""
    try:
        # Use ip command to get the IP address
        output = subprocess.check_output(['ip', 'addr', 'show', interface]).decode()
        for line in output.split('\n'):
            if 'inet ' in line:
                return line.split()[1].split('/')[0]
    except Exception:
        return None  # Return None if IP address could not be found
def get_dynamic_network_info():
    """Return a dictionary with dynamic network info."""
    network_info = {}
    interfaces = get_network_interfaces()
    
    for interface in interfaces:
        mac = get_mac_address(interface)
        ip = get_ip_address(interface)
        if mac and ip:
            network_info[interface] = {'mac': mac, 'ip': ip}
    
    return network_info
