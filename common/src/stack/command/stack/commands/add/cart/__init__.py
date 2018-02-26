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
	Add a cart.
	
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
	Add multiple carts from a file with urls.
	</param>

	<param type='string' name='downloaddir'>
	Directory to download to. Defaults /tmp.
	</param>

	<param type='string' name='service'>
	Github, www, artifactory, etc.
	Artifactory is default for our corporate
	overlords.
	Can we do a straigt clone without src?
	</param>
	"""

	def fixPerms(self,cart):
		# make sure apache can read all the files and directories
		gr_name, gr_passwd, gr_gid, gr_mem = grp.getgrnam('apache')

		cartpath = '/export/stack/carts/%s' % cart

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
		filename, url, urlfile, dldir, service = self.fillParams([('file', None),
						('url', None),
						('urlfile', None),
						('downloaddir', '/tmp/'),
						('service', 'artifactory')
						])

		carts = args
		if url == None and urlfile == None and filename == None:
			if not len(carts):
				raise ArgRequired(self, 'cart')
			else:
				for cart in carts:
					self.runImplementation('default', cart)
					self.fixPerms(cart)
		else:
			print('network')
			self.runImplementation('network_cart', (url,urlfile,service))
#			self.fixPerms(cart)
		

