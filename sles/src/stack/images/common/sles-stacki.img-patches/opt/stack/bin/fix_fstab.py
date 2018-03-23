#!/opt/stack/bin/python3 -E
"""Fixes the autoyast partitioning if nukedisks=False
Replaces UUID with LABEL and applies label to relevant partition
"""
import sys
import subprocess
import os
import fileinput
try:
	sys.path.append('/tmp')
	from fstab_info import old_fstab
except ModuleNotFoundError:
	# If the file isn't there to import then we didn't do a nukedisks=false
	sys.exit(0)
except ImportError:
	sys.exit(0)


def get_host_partition_devices(detected_disks):
	"""
	Returns the device names of all the partitions on a specific disk
	"""

	devices = []
	p = subprocess.Popen(
			['lsblk', '-nrio', 'NAME', '/dev/%s' % detected_disks],
			stdin=subprocess.PIPE, stdout=subprocess.PIPE,
			stderr=subprocess.PIPE)
	o = p.communicate()[0]
	out = o.decode()

	for l in out.split('\n'):
		# Ignore empty lines
		if not l.strip():
			continue

		# Skip read-only and removable devices
		arr = l.split()
		diskname = arr[0].strip()

		if diskname != detected_disks:
			devices.append(diskname)

	return devices


def get_host_fstab():
	"""Get contents of /etc/fstab by mounting all disks
	and checking if /etc/fstab exists.
	"""
	host_fstab = []
	fstab = '/mnt/etc/fstab'

	if os.path.exists(fstab):
		file = open(fstab)

		for line in file.readlines():
			entry = {}

			split_line = line.split()
			if len(split_line) < 3:
				continue

			entry['device'] = split_line[0].strip()
			entry['mountpoint'] = split_line[1].strip()
			entry['fstype'] = split_line[2].strip()

			host_fstab.append(entry)

		file.close()

	return host_fstab


def get_existing_labels(yast_fstab, existing_fstab):
	"""Compare the two fstab inputs to determine which didn't have their LABEL= applied from autoyast.
	Returns a new list of dictionaries that contains the new UUID and the fstype"""
	no_labels = []
	existing_labels = []
	new_data = {}

	for mount in yast_fstab:
		if 'uuid' in mount['device'].lower():
			# Create list to check against old_fstab
			no_labels.append(mount['mountpoint'])
			# Capture new data based on mountpoint key
			new_data[mount['mountpoint']] = [mount['device'], mount['fstype']]

	for mount in existing_fstab:
		if 'label' in mount['device'].lower() and mount['mountpoint'] in no_labels:
			if mount['fstype'] != new_data[mount['mountpoint']][1]:
				print("fstype changed during reinstall!")
			else:
				mount['new_uuid'] = new_data[mount['mountpoint']][0]
				mount['new_fstype'] = new_data[mount['mountpoint']][1]
				existing_labels.append(mount)

	return existing_labels


def edit_fstab(find, replace):
	"""Edit the /mnt/etc/fstab to replace the UUID= with LABEL=."""
	with fileinput.FileInput('/mnt/etc/fstab', inplace=True) as fstab:
		for line in fstab:
			if find in line:
				print(line.replace('UUID=%s' % find, 'LABEL=%s' % replace), end='')
			# leave the line alone
			else:
				print(line, end='')


new_fstab = get_host_fstab()
partitions_to_label = get_existing_labels(new_fstab, old_fstab)
# We may have to order the for loop if we have mount points within mount points on xfs.
for partition in partitions_to_label:
	if len(partition) == 5:
		edit_fstab(partition['new_uuid'],  partition['device'])
# Need output of the partitions_to_label to be utilized for post autoyast script.
if not os.path.exists('/tmp/fstab_info'):
	os.makedirs('/tmp/fstab_info')
with open('/tmp/fstab_info/__init__.py', 'a') as fstab_info:
	fstab_info.write('partitions_to_label = %s\n\n' % partitions_to_label)
