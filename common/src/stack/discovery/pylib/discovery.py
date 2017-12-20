# @copyright@
# Copyright (c) 2006 - 2017 Teradata
# All rights reserved. Stacki(r) v5.x stacki.com
# https://github.com/Teradata/stacki/blob/master/LICENSE.txt
# @copyright@

import asyncio
import ipaddress
from itertools import filterfalse
import logging
from logging.handlers import RotatingFileHandler
import os
import pymysql
import re
import signal
import subprocess
import sys

from stack.api.get import GetAttr

class Discovery:
    """
    Start or stop a daemon that listens for PXE boots and inserts the new
    nodes into the database.
    """

    _PIDFILE = "/var/run/stack-discovery.pid"
    _LOGFILE = "/var/log/stack-discovery.log"

    _get_next_ip_address_cache = {}
    _get_ipv4_network_for_interface_cache = {}

    @property
    def hostname(self):
        return f"{self._base_name}-{self._rack}-{self._rank}"

    def _get_ipv4_network_for_interface(self, interface):
        """
        Return an IPv4Network object for a given interface, caching the results in the process.
        """

        ipv4_network = self._get_ipv4_network_for_interface_cache.get(interface)
        
        # If we don't have a network in the cache, create it
        if ipv4_network is None:
            results = subprocess.run(
                ["ip", "-o", "-4", "address"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                encoding="utf-8"
            )            
            for line in results.stdout.splitlines():
                match = re.match(r'\d+:\s+(\S+)\s+inet\s+(\S+)', line)
                if match:
                    if match.group(1) == interface:
                        ipv4_network = ipaddress.IPv4Interface(match.group(2)).network
                        self._get_ipv4_network_for_interface_cache[interface] = ipv4_network

                        self._logger.debug("found network: %s", ipv4_network)
                        break
                else:
                    self._logger.debug("ip regex didn't match line: %s", line)
        
        return ipv4_network        

    def _get_hosts_for_interface(self, interface):
        """
        Get a iterator of IPv4Address objects for this interface, if it exists in the database
        and is pxe bootable. If it isn't a valid interface, return None.
        """

        # Get an IPv4Network for this interface passed in
        ipv4_network = self._get_ipv4_network_for_interface(interface)
        
        if ipv4_network is not None:
            # Figure out the gateway for the interface and check that pxe is true
            with connection.cursor() as cursor:
                if cursor.execute(
                    "SELECT gateway, pxe FROM subnets WHERE address=%s AND mask=%s",
                    (str(ipv4_network.network_address), str(ipv4_network.netmask))
                ) != 0:
                    gateway, pxe = cursor.fetchone()
                    if pxe == 1:
                        # Make sure to filter out the gateway IP address
                        gateway = ipaddress.IPv4Address(gateway)
                        return filterfalse(lambda x: x == gateway, ipv4_network.hosts())
                    else:
                        self._logger.warning("pxe not enabled on interface: %s", interface)
                else:
                    self._logger.warning("unknown network for interface: %s", interface)
        
        # We couldn't find the network or it wasn't pxe enabled
        return None

    def _get_next_ip_address(self, interface):
        """
        Get the next available IP address for the network on the provided interface.
        Return None if we are out of IP addresses or if the interface is not valid.
        """

        # See if we need to get the hosts() iterator for this interface
        if interface not in self._get_next_ip_address_cache:
            # Get the hosts iterator for this interface, return None if it isn't valid
            hosts = self._get_hosts_for_interface(interface)
            if hosts is None:
                return None

            self._get_next_ip_address_cache[interface] = hosts

        # Find the next available IP address
        for ip_address in self._get_next_ip_address_cache[interface]:
            self._logger.debug("trying IP address: %s", ip_address)
            
            # Make sure this IP isn't already taken
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT count(id) FROM networks WHERE ip=%s AND (device is NULL or device NOT LIKE 'vlan%%')",
                    (str(ip_address),)
                )

                if cursor.fetchone()[0] == 0:
                        # Looks like it is free
                        self._logger.debug("IP address is free: %s", ip_address)

                        return ip_address
                else:
                    self._logger.debug("IP address already taken: %s", ip_address)
            
        # No IP addresses left
        return None

    def _add_node(self, interface, mac_address, ip_address):
        # Figure out the network for this interface
        network = None
        ipv4_network = self._get_ipv4_network_for_interface(interface)
        if ipv4_network is not None: 
            with connection.cursor() as cursor:
                if cursor.execute(
                    "SELECT name FROM subnets WHERE address=%s AND mask=%s",
                    (str(ipv4_network.network_address), str(ipv4_network.netmask))
                ) != 0:
                    network = cursor.fetchone()[0]
        
        # The network should alway be able to be found, unless something deleted it since the 
        # discovery daemon started running
        if network is not None:
            # Add our new node
            result = subprocess.run([
                "/opt/stack/bin/stack",
                "add",
                "host",
                self.hostname,
                f"appliance={self._appliance_name}",
                f"rack={self._rack}",
                f"rank={self._rank}",
                f"box={self._box}"
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8")
            
            if result.returncode != 0:
                self._logger.error("failed to add host %s:\n%s", self.hostname, result.stderr)
                return

            # Add the node's interface
            result = subprocess.run([
                "/opt/stack/bin/stack",
                "add",
                "host",
                "interface",
                self.hostname,
                "interface=NULL",
                "default=true",
                f"mac={mac_address}",
                f"name={self.hostname}",
                f"ip={ip_address}",
                f"network={network}"
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8")
            
            if result.returncode != 0:
                self._logger.error("failed to add interface for host %s:\n%s", self.hostname, result.stderr)
                return
            
            # Set the new node's install action
            result = subprocess.run([
                "/opt/stack/bin/stack",
                "set",
                "host",
                "installaction",
                self.hostname,
                f"action={self._install_action}"
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8")
            
            if result.returncode != 0:
                self._logger.error("failed to set install action for host %s:\n%s", self.hostname, result.stderr)
                return

            # Set the net node to install on boot
            result = subprocess.run([
                "/opt/stack/bin/stack",
                "set",
                "host",
                "boot",
                self.hostname,
                "action=install"
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8")
            
            if result.returncode != 0:
                self._logger.error("failed to set boot action for host %s:\n%s", self.hostname, result.stderr)
                return

            # Sync the global config
            result = subprocess.run([
                "/opt/stack/bin/stack",
                "sync",
                "config"
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8")
            
            if result.returncode != 0:
                self._logger.error("unable to sync global config:\n%s", result.stderr)
                return

            # Sync the host config
            result = subprocess.run([
                "/opt/stack/bin/stack",
                "sync",
                "host",
                "config",
                self.hostname
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8")
            
            if result.returncode != 0:
                self._logger.error("unable to sync global host config:\n%s", result.stderr)
                return

            self._logger.info("successfully added host %s", self.hostname)
        else:
            self._logger.error("no network exists for interface %s", interface)

    def _process_dhcp_line(self, line):
        # See if we are a DHCPDISCOVER message
        match = re.search(r"DHCPDISCOVER from ([0-9a-f:]{17}) via (\S+)(:|$)", line)
        if match:
            mac_address = match.group(1)
            interface = match.group(2)

            self._logger.info("detected a dhcp request: %s %s", mac_address, interface)

            # Is this a new MAC address?
            with self._connection.cursor() as cursor:
                cursor.execute("SELECT count(id) FROM networks WHERE mac=%s", (mac_address,))
                if cursor.fetchone()[0] == 0:
                    # It is a new node
                    self._logger.info("found a new node: %s %s", mac_address, interface)

                    # Make sure we have an IP for it
                    ip_address = self._get_next_ip_address(interface)
                    if ip_address is None:
                        self._logger.error("no IP addresses available for interface %s", interface)
                    else:
                        # Add the new node
                        self._add_node(interface, mac_address, ip_address)

                        # Increment the rank
                        self._rank += 1
                else:
                    self._logger.debug("node is already known: %s %s", mac_address, interface)

        else:
            if "DHCPDISCOVER" in line:
                self._logger.warning("DHCPDISCOVER found in line but didn't match regex:\n%s", line)

    def _process_kickstart_line(self, line):
        if re.search("install/sbin(/public)?/profile.cgi", line):
            self._logger.debug("KICKSTART: %s", line)

    async def _monitor_log(self, log_path, process_line):
        # Open our log file
        with open(log_path, 'r') as log:
            # Move to the end
            log.seek(0, 2)

            # Start looking for new lines in the log file
            while not self._done:
                line = log.readline()
                
                if line:
                    process_line(line)
                else:
                    await asyncio.sleep(1)
    
    def _cleanup(self):
        try:
            os.remove(self._PIDFILE)
        except:
            pass

    def _signal_handler(self):
        self._done = True
    
    def _get_pid(self):
        pid = None
        if os.path.exists(self._PIDFILE):
            with open(self._PIDFILE, 'r') as f:
                pid = int(f.read())
        
        return pid
    
    def __init__(self, logging_level=logging.INFO):
        # Set up our logger
        formatter = logging.Formatter("%(asctime)s %(levelname)s: %(message)s", "%Y-%m-%d %H:%M:%S")

        try:
            handler = RotatingFileHandler(
                self._LOGFILE,
                maxBytes=10*1024*1024,
                backupCount=3
            )
            handler.setFormatter(formatter)
        except PermissionError:
            # We don't have write access to the logfile, so just blackhole logs
            handler = logging.NullHandler()

        self._logger = logging.getLogger("discovery")
        self._logger.setLevel(logging_level)
        self._logger.addHandler(handler)
    
    def is_running(self):
        "Check if the daemon is running."

        # Is our pidfile there?
        pid = self._get_pid()

        if pid is not None:
            # Is the process still running?
            if os.path.isdir(f"/proc/{pid}"):
                return True
            else:
                # The process no longer exists, clean up the old files
                self._cleanup()

        return False

    def start(self, connection, appliance_name=None, appliance_long_name=None,
        base_name=None, rack=None, rank=None, box=None, install_action=None):    
        """
        Start the node discovery daemon.
        """

        # Only start if there isn't already a daemon running
        if not self.is_running() and connection is not None:
            # Make sure either appliance_name or appliance_long_name is set
            if appliance_name and appliance_long_name:
                raise ValueError("Only one of application_name and appliance_long_name may be set") 

            # Find the appliance id and, if needed, appliance name
            if appliance_name:
                with connection.cursor() as cursor:
                    if cursor.execute("SELECT id FROM appliances WHERE name=%s", (appliance_name,)) != 0:
                        self._appliance_id = cursor.fetchone()[0]
                        self._appliance_name = appliance_name
                    else:
                        raise ValueError(f"Unknown appliance with name {appliance_name}")

            elif appliance_long_name:
                with connection.cursor() as cursor:
                    if cursor.execute(
                        "SELECT id, name FROM appliances WHERE longname=%s",
                        (appliance_long_name,)
                    ) != 0:
                        self._appliance_id, self._appliance_name = cursor.fetchone()
                    else:
                        raise ValueError(f"Unknown appliance with long name {appliance_long_name}")
            
            else:
                raise ValueError("One of either appliance_name or appliance_long_name needs to be set")
            
            # Set up the base name
            if base_name:
                self._base_name = base_name
            else:
                self._base_name = self._appliance_name
            
            # Set up the rack
            if rack is None:
                self._rack = int(GetAttr("discovery.base.rack"))
            else:
                self._rack = int(rack)
            
            # Set up the rank
            if rank is None:
                # Start with with default
                self._rank = int(GetAttr("discovery.base.rank"))

                # Try to pull the next rank from the DB
                with connection.cursor() as cursor:
                    if cursor.execute(
                        "SELECT max(rank) FROM nodes WHERE appliance=%s AND rack=%s",
                        (self._appliance_id, self._rack)
                    ):
                        max_rank = cursor.fetchone()[0]
                        if max_rank is not None:
                            self._rank = int(max_rank) + 1  
            else:
                self._rank = int(rank)
            
            # Set up box and make sure it is valid
            if box is None:
                self._box = "default"
            else:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT count(id) FROM boxes WHERE name=%s", (box,))
                    if cursor.fetchone()[0] != 0:
                        self._box = box
                    else:
                        raise ValueError("Box does not exist")
            
            # Set up install_action and make sure is is valid
            if install_action is None:
                self._install_action = "default"
            else:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT count(id) FROM bootnames WHERE type='install' and name=%s",
                        (install_action,)
                    )
                    if cursor.fetchone()[0] != 0:
                        self._install_action = install_action
                    else:
                        raise ValueError("Install action is does not exist")
            
            # Find our apache log
            if os.path.isfile("/var/log/httpd/ssl_access_log"):
                kickstart_log = "/var/log/httpd/ssl_access_log"
            elif os.path.isfile("/var/log/apache2/ssl_access_log"):
                kickstart_log = "/var/log/apache2/ssl_access_log"
            else:
                raise ValueError("Apache log does not exist")
            
            # Fork once to get us into the background
            if os.fork() != 0:
                return
            
            # Seperate ourselves from the parent process
            os.setsid()

            # Fork again so we aren't a session leader
            if os.fork() != 0:
                return
            
            # Run connection on the connection passed in, so when the parent process closes theirs, we still have one
            self._connection = connection
            self._connection.connect()

            # Now write out the daemon pid
            with open(self._PIDFILE, 'w') as f:
                f.write("{}".format(os.getpid()))
            
            self._logger.info("discovery daemon started")

            # Get our coroutine event loop
            loop = asyncio.get_event_loop()

            # Setup signal handlers to cleanly stop
            loop.add_signal_handler(signal.SIGINT, self._signal_handler)
            loop.add_signal_handler(signal.SIGTERM, self._signal_handler)

            # Start our event loop
            status_code = 0
            self._done = False
            try:
                loop.run_until_complete(asyncio.gather(
                    self._monitor_log("/var/log/messages", self._process_dhcp_line),
                    self._monitor_log(kickstart_log, self._process_kickstart_line)
                ))
            except:
                self._logger.exception("event loop threw an exception")
                status_code = 1
            finally:
                # All done, clean up
                loop.close()
                self._connection.close()
                self._cleanup()
            
            self._logger.info("discovery daemon stopped")

            sys.exit(status_code)

    def stop(self):
        "Stop the node discovery daemon."

        if self.is_running():
            try:
                os.kill(self._get_pid(), signal.SIGTERM)
            except OSError as e:
                self._logger.exception("unable to stop discovery daemon")
                return False
        
        return True


if __name__ == "__main__":
    discovery = Discovery(logging_level=logging.DEBUG)

    if sys.argv[1] == "--start":
        # Start needs a database connection
    
        # Figure out the mysql password, if possible
        password = None
        with open("/opt/stack/etc/my.cnf", 'r') as f:
            for line in f:
                if line.startswith("password"):
                    password = line.split('=')[1].strip()
                    break
        
        if password is None:
            print("Error: unable to connect to the database", file=sys.stderr)
            sys.exit(1)
        
        # Try to connect to Mysql
        connection = pymysql.connect(
            db="cluster",
            host="localhost",
            user="apache",
            passwd=password,
            unix_socket="/var/opt/stack/mysql/mysql.sock",
            autocommit=True
        )
        
        # Start the discovery daemon
        discovery.start(connection, appliance_name="backend")

        # Close the DB connection
        connection.close()
    
    elif sys.argv[1] == "--stop":
        # Try to stop the discovery daemon
        if not discovery.stop():
            print("Error: unable to stop discovery daemon", file=sys.stderr)
            sys.exit(1)
    
    elif sys.argv[1] == "--status":
        # Figure out the discovery daemon status
        if discovery.is_running():
            print("Status: daemon is running")
        else:
            print("Status: daemon is stopped")

    sys.exit(0)
