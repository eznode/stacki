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
	Add a cart from a compressed file.
	"""		
	def run(self, args):
		filename = args
		self.owner.call('unpack.cart', ['file=%s' % filename])
