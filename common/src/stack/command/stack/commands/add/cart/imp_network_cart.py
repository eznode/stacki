# @copyright@
# Copyright (c) 2006 - 2018 Teradata
# All rights reserved. Stacki(r) v5.x stacki.com
# https://github.com/Teradata/stacki/blob/master/LICENSE.txt
# @copyright@

import os.path
import sys
import stack.file
import stack.commands
import json
import subprocess
import time
from stack.exception import CommandError

class Implementation(stack.commands.Implementation):
	"""
	Add a cart from the network
	"""			
	def get_auth_info(self,authfile):
		curl_args = []

		if not os.path.exists(authfile):
			msg = '%s file not found' % authfile
			raise CommandError(self, msg)

		with open(authfile, 'r') as a:
			auth = json.load(a)

		if not auth:
			sys.stderr.write("Cannot read auth file %s\n" % \
				(authfile))
		try:
			base = auth['urlbase']
			urlfiles = auth['files']
			return(base,urlfiles,auth['username'],auth['password'])
		except:
			return(None,None,auth['username'],auth['password'])

	def download_url(self, url, dest, curl_cmd):
		# Retry the curl command 3 times, in case of error
		retry = 3
		while retry:
			p = subprocess.Popen(curl_cmd,
				stdout=subprocess.PIPE,
				stderr=subprocess.PIPE)
			rc = p.wait()
			o, e = p.communicate()
			if rc:
				retry = retry - 1
				print(e)
				time.sleep(1)
			else:
				if o.strip() == '200':
					retry = 0
				else:
					retry = retry - 1
					print("Error: Cannot download. HTTP STATUS: %s" % o)
					if os.path.exists(dest):
						os.unlink(dest)
					time.sleep(1)

	def get_cmd(self,user,passwordauthfile):
		cmd='curl -kSs --retry 3 -w %{http_code} '
		if authfile == None:
			return(cmd)
		else:
			user,password = self.get_auth_info(authfile)
			cmd += "--user %s:'%s' " % (user,password)
			return(cmd)

	def run(self, args):
		url, urlfile, dldir, authfile = args
		urls = []
		# gather urls.
		if urlfile != None:
			with open(urlfile,'r') as f:
				urls = f.readlines()
			f.close()
			
		if url != None:
			urls.append(url)

		# check for urls in the json file
		if authfile:
			base,urlfiles,user,passwd = self.get_auth_info(authfile)
		else:
			base = urlfiles = user = password = None

		# if there's a user and a password, add to curl args
		if user and passwd:
			curl_args = "--user %s:'%s' " % (user,passwd)
		else:
			curl_args = None

		# authfile might not have a base or urlfiles
		# we are requiring both.
		if base == None or urlfiles == None:
			pass
		else:
			for url in urlfiles:
				urls.append('%s/%s' % (base,url))

			
		for url in urls:
			url = url.strip('\n')
			cmd = 'curl -kSs --retry 3 -w %{http_code} '
			if curl_args:
				cmd += curl_args

			cartname = os.path.basename(url)
			dest = '%s/%s' % (dldir,cartname)
			cmd += " %s -o %s" % (url, dest)
			self.download_url(url.strip('\n'), dest, cmd.split())
#			# unpack the cart
			self.owner.call('unpack.cart', ['file=%s' % dest])
