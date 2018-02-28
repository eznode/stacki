# @copyright@
# Copyright (c) 2006 - 2018 Teradata
# All rights reserved. Stacki(r) v5.x stacki.com
# https://github.com/Teradata/stacki/blob/master/LICENSE.txt
# @copyright@

import os
import grp
import stat
import stack.file
import stack.commands
from stack.exception import ArgRequired, ArgUnique, CommandError


class Command(stack.commands.CartArgumentProcessor,
	stack.commands.add.command):
	"""
	Add a cart. Files to download are concatenated
	from "url," "urlfile," and "authfile" options
	if any files are designated in the authfile.
	
	<arg type='string' name='cart' optional='1'>
	The name of the cart to be created.
	</arg>

	<param type='string' name='file'>
	Add a local cart from a compressed file.
	</param>

	<param type='string' name='url'>
	Add cart from a single url.
	</param>

	<param type='string' name='urlfile'>
	Add multiple carts from a text with urls.
	</param>

	<param type='string' name='downloaddir'>
	Directory to download to. Defaults /tmp.
	</param>

	<param type='string' name='authfile'>
	Json formatted authentication file.
	Username/password. Yoy
	supported.
	</param>

	<example cmd="add cart urlfile=/tmp/tdurls downloaddir=/export authfile=/root/carts.json">
	Download the carts in /tmp/tdurls into /export.
	Use the username/password in /root/carts.json.

	Example json looks like this:
	{
        "username":"myuserid",
        "password":"mypassword"
	}

	You can also include urls in the json file.e
	{
	        "username":"myuserid",
		"password":"mypassword",
	        "urlbase": "https://sdartifact.td.teradata.com/artifactory",
	        "files": [ "pkgs-generic-snapshot-sd/stacki-5/kubernetes/kubernetes-stacki5-12.02.18.02.12-rc3.tgz" ]
	}
	</example>
	"""

	def fixPerms(self):
		# make sure apache can read all the files and directories
		gr_name, gr_passwd, gr_gid, gr_mem = grp.getgrnam('apache')

		cartpath = '/export/stack/carts/'

		for dirpath, dirnames, filenames in os.walk(cartpath):
			try:
				os.chown(dirpath, -1, gr_gid)
			except:
				pass

			perms = os.stat(dirpath)[stat.ST_MODE]
			perms = perms | stat.S_IRGRP | stat.S_IXGRP

			#
			# apache needs to be able to write in the cart directory
			# when carts are compiled on the fly
			#
			if dirpath == cartpath:
				perms |= stat.S_IWGRP

			try:
				os.chmod(dirpath, perms)
			except:
				pass

			for file in filenames:
				filepath = os.path.join(dirpath, file)

				try:
					os.chown(filepath, -1, gr_gid)
				except:
					pass

				perms = os.stat(filepath)[stat.ST_MODE]
				perms = perms | stat.S_IRGRP

				try:
					os.chmod(filepath, perms)
				except:
					pass
	def run(self, params, args):
		filename, url, urlfile, dldir, authfile = self.fillParams([('file', None),
						('url', None),
						('urlfile', None),
						('downloaddir', '/tmp/'),
						('authfile', None) 
						])

		carts = args

		if filename != None and len(filename) > 0:
			self.runImplementation('local_cart', filename)

		if url == urlfile == filename == authfile == None:
			if not len(carts):
				raise ArgRequired(self, 'cart')
			else:
				for cart in carts:
					self.runImplementation('default', cart)
		else:
			self.runImplementation('network_cart', (url,urlfile,dldir,authfile))
		# dude, we have know idea if they saved the correct perms - fix it.
		self.fixPerms()
