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
	from fstab_info import partitions_to_label
except ModuleNotFoundError:
	# If the file isn't there to import then we didn't do a nukedisks=false
	sys.exit(0)

def label_partition(partition):
	"""Determine the filesystem type and take appropriate steps to add a label.
	Assumes the partition being input has the following keys containing data similar to below:
	['device'] = "LABEL=VARBE1"
	['new_uuid'] = "UUID=FFFFFFFFFFFFFFFFFFFF"
	['fstype'] = "ext3"
	['mountpoint'] = "/var"

	Only handles xfs and ext formats.
	The btrfs will remain with it's UUID mount reference
	"""
	label = partition['device'].split('=')[1]
	uuid = partition['new_uuid'].split('=')[1]
	if 'ext' in partition['fstype'].lower():
		return_code = subprocess.call(['e2label', '/dev/disk/by-uuid/%s' % uuid, '%s' % label])
		print(return_code)
		if return_code == 0:
			edit_fstab(label, uuid)
	if 'xfs' in partition['fstype'].lower():
		# This better be unmount or we will have issues.
		# edit the partition
		return_code = subprocess.call(['xfs_admin', ' -L', '"%s"' % label, '/dev/disk/by-uuid/%s' % uuid])


for partition in partitions_to_label:
	if len(partition) == 5:
		label_partition(partition)