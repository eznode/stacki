# @copyright@
# Copyright (c) 2006 - 2018 Teradata
# All rights reserved. Stacki(r) v5.x stacki.com
# https://github.com/Teradata/stacki/blob/master/LICENSE.txt
# @copyright@

import os
import grp
import stat
import tarfile
import stack.file
import stack.commands
from pathlib import Path
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
		# This is the atomic bomb change permissions because 
		# it changes everything to root:apache in /export/stack/carts
		gr_name, gr_passwd, gr_gid, gr_mem = grp.getgrnam('apache')

		cartpath = '/export/stack/carts/'

		for dirpath, dirnames, cartfiles in os.walk(cartpath):
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

			for file in cartfiles:
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

	def checkCart(self,cartfile):
		req =  ['RPMS', 'graph', 'nodes']
		if tarfile.is_tarfile(cartfile) == True:
			with tarfile.open(cartfile,'r|*') as tar:
				files = tar.getmembers()
				dirs = [ os.path.split(f.name)[-1] \
					for f in files if f.isdir() == True ]
				if set(req).issubset(set(dirs)) == True:
					return True
				else:
					diff = set(req).difference(set(dirs))
					msg = "You're missing an %s " % diff
					msg += "dir in your cart"
					raise CommandError(self,msg)
					return False
		else:
			return False

	def unpackCart(self, cart, cartfile, cartsdir):
		with tarfile.open(cartfile,'r:*') as tar:
			if self.checkCart(cartfile) == True:
				print("Unpacking....%s" % cart)
				tar.extractall(cartsdir)
				print("\nUnpacked!")
				return True
			else:
				print("That's no cart tarfile!")
				print("Removing %s" % cart)
				self.removeCart(cart)
				return False
		tar.close()

	def createFiles(self, name, path):

		# write the graph file
		graph = open(os.path.join(path, 'graph', 'cart-%s.xml' % name), 'w')
		graph.write('<graph>\n\n')
		graph.write('\t<description>\n\t%s cart\n\t</description>\n\n' % name)
		graph.write('\t<order head="backend" tail="cart-%s-backend"/>\n' % name)
		graph.write('\t<edge  from="backend"   to="cart-%s-backend"/>\n\n' % name)
		graph.write('</graph>\n')
		graph.close()

		# write the node file
		node = open(os.path.join(path, 'nodes', 'cart-%s-backend.xml' % name), 'w')
		node.write('<stack:stack>\n\n')
		node.write('\t<stack:description>\n')
		node.write('\t%s cart backend appliance extensions\n' % name)
		node.write('\t</stack:description>\n\n')
		node.write('\t<stack:package><!-- add packages here --></stack:package>\n\n')
		node.write('<stack:script stack:stage="install-post">\n')
		node.write('<!-- add shell code for post install configuration -->\n')
		node.write('</stack:script>\n\n')
		node.write('</stack:stack>\n')
		node.close()

	def addCart(self,cart):
		for row in self.db.select("""
			* from carts where name = '%s'
			""" % cart):
			raise CommandError(self, '"%s" cart exists' % cart)

		# If the directory does not exist create it along with
		# a skeleton template.

		tree = stack.file.Tree('/export/stack/carts')
		if cart not in tree.getDirs():
			for dir in [ 'RPMS', 'nodes', 'graph' ]:
				os.makedirs(os.path.join(tree.getRoot(), cart, dir))

			cartpath = os.path.join(tree.getRoot(), cart)
			args = [ cart, cartpath ]
			self.createFiles(cart, cartpath)

		# Files were already on disk either manually created or by the
		# simple template above.
		# Add the cart to the database so we can enable it for a box

		self.db.execute("""
			insert into carts(name) values ('%s')
			""" % cart)
		
	def addCartFile(self,cartfile):
		cartsdir = '/export/stack/carts/'
		# if multiple suffixes, increment to remove
		# the right number to create the correct cart.
		comp_type = ['.gz', '.tgz', '.tar' ]
		suff = Path(cartfile).suffixes
		snum = 0
		for s in suff:
			if s in comp_type:
				snum += 1

		fbase = os.path.basename(cartfile).rsplit('.',snum)[0]
		# This fixes people's stupid.
		# take care of when the cart isn't packed right
		with tarfile.open(cartfile,'r:*') as tar:
			tardir = tar.getnames()[0]
		tar.close()

		if tardir == fbase:
			cart = fbase
		elif tardir == 'RPMS':
			cart = fbase
			cartsdir = cartsdir + '%s' % fbase
		else:
			cart = tardir

		self.addCart(cart)
		self.unpackCart(cart, cartfile, cartsdir)
		
	def run(self, params, args):
		cartfile, url, urlfile, dldir, authfile = \
			self.fillParams([('file', None),
					('url', None),
					('urlfile', None),
					('downloaddir', '/tmp/'),
					('authfile', None) 
					])

		carts = args

		# check if we are creating a new cart
		if url == urlfile == cartfile == authfile == None:
			if not len(carts):
				raise ArgRequired(self, 'cart')
			else:
				for cart in carts:
					self.addCart(cart)

		# If there's a filename, check it.
		if cartfile == None:
			pass
		elif Path(cartfile).exists() == True \
			and Path(cartfile).is_file() == True:
		# If there is a filename, make sure it's a tar gz file.	
			if self.checkCart(cartfile) == True:
				self.addCartFile(cartfile)
			else:
				msg = '%s is not a cart.' % cartfile
				raise CommandError(self,msg)
		else:
			print('biteme')
			msg = '%s was not found.' % cartfile
			raise CommandError(self,msg)

		# do the network cart if url or urlfile or authfile exist.
		if url != None or urlfile != None or authfile != None:
			print("running network cart")
			# download the carts.
			# then addCartFile to them.
			cartfile = self.runImplementation('network_cart', (url,urlfile,dldir,authfile))
			print(cartfile)
			self.addCartFile(cartfile)

		# Fix all the perms all the time.
		self.fixPerms()
