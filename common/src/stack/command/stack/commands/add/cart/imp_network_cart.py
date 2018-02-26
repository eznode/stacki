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


class Implementation(stack.commands.Implementation):
	"""
	Add a cart from the network
	"""		

	def getServiceCommand(self,service):
		if service == 'artifactory':
			print('pulling from artifactory')
			cmd = 'jfrog rt dl --flat True ' 
			return(cmd)

		elif service == 'git':
			print('pulling from git')
			cmd='git '
			return(cmd)
		elif service == 'git-clone':
			print('pulling from git')
			cmd='git clone '
			return(cmd)
		elif service in [ 'http', 'https']:
			print('pulling from web')
			cmd='curl -kSs ' % service
			return(cmd)
		else:
			msg = '%s ' % service
			msg += "service not recognized."
			raise CommandError(self,msg)

	def run(self, args):
		url, urlfile, service, dldir = args
		urls = []
		if urlfile != None:
			with open(urlfile,'r') as f:
				urls = f.readlines()
			f.close()
			
		if url != None:
			urls.append(url)
		
		svcmd = self.getServiceCommand(service)

		for url in urls:
			cmd = svcmd + url + dldir
			print(cmd)
	
	# get the cart
	# check the url given
	# unpack the cart
