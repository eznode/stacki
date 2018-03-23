#!/opt/stack/bin/python3 -E
import sys
import subprocess
import os
import fileinput
sys.path.append('/opt/stack/lib')
from stacki_default_part import sles

try:
	sys.path.append('/tmp')
	from fstab_info import old_fstab
except ModuleNotFoundError:
	# If the file isn't there to import then we didn't do a nukedisks=false
	sys.exit(0)


def get_host_disks():
	"""Returns list of disks on this machine"""

	disks = []
	p = subprocess.Popen(
			['lsblk', '-nio', 'NAME,RM,RO'],
			stdin=subprocess.PIPE, stdout=subprocess.PIPE,
			stderr=subprocess.PIPE)
	o = p.communicate()[0]
	out = o.decode()
	
	for line in out.split('\n'):
		# Ignore empty lines
		if not line.strip():
			continue
		# Skip read-only and removable devices
		arr = line.split()
		removable = arr[1].strip()
		readonly = arr[2].strip()

		if removable == "1" or readonly == "1":
			continue

		diskname = arr[0].strip()

		if diskname[0] in ['|', '`']:
			continue

		disks.append(diskname)

	return disks


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


def get_host_fstab(disks):
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


def get_existing_labels(new_fstab, old_fstab):
	no_labels = []
	existing_labels = []
	new_data = {}

	for mount in new_fstab:
		if 'uuid' in mount['device'].lower():
			# Create list to check against old_fstab
			no_labels.append(mount['mountpoint'])
			# Capture new data based on mountpoint key
			new_data[mount['mountpoint']] = [mount['device'], mount['fstype']]
			print(new_data)

	for mount in old_fstab:
		if 'label' in mount['device'].lower() and mount['mountpoint'] in no_labels:
			if mount['fstype'] != new_data[mount['mountpoint']][1]:
				print("fstype changed during reinstall!")
			else:
				mount['new_uuid'] = new_data[mount['mountpoint']][0]
				mount['new_fstype'] = new_data[mount['mountpoint']][1]
				existing_labels.append(mount)

	return existing_labels


def edit_fstab(label, uuid):
	with fileinput.FileInput('/mnt/etc/fstab', inplace=True, backup='.bak') as fstab:
		for line in fstab:
			if uuid in line:
				print(line.replace('UUID=%s' % uuid, "LABEL=%s" % label), end='')
			# leave the line alone
			else:
				print(line, end='')


def label_partition(partition)
	label = partition['device'].split('=')[1]
	uuid = partition['new_uuid'].split('=')[1]
	if 'ext' in partition['fstype'].lower():
		return_code = subprocess.call(['e2label', '/dev/disk/by-uuid/%s' % uuid, '%s' % label])
		print(return_code)
		if return_code == 0:
			edit_fstab(label, uuid)
	if 'xfs' in partition['fstype'].lower():
		# unmount
		return_code = subprocess.call(['umount', '/dev/disk/by-uuid/%s' % uuid])
		print(return_code)
		# then edit
		return_code = subprocess.call(['e2label', '/dev/disk/by-uuid/%s' % uuid, '%s' % label])
		print(return_code)
		# mount it back
		return_code = subprocess.call(['umount', '/dev/disk/by-uuid/%s' % uuid])
		print(return_code)
		if return_code == 0:
			edit_fstab(label, uuid)


new_fstab = get_host_fstab(get_host_disks())
existing_labels = get_existing_labels(new_fstab, old_fstab)
print(existing_labels)

for partition in existing_labels:
	if len(disk) == 5:
		label_partition(partition)
#

#
#
# Comparing the new to old fstab
# if new_fstab in old_fstab['mountpoint']:
# 	print("Found matching mount points")
#
# # Making changes to the labels
# missing_labels = {}
# for disk in missing_labels:
# 	print("%s %s" % (disk, missing_labels['label']))

# Rewriting the new_fstab
