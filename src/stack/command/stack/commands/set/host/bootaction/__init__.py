# @SI_Copyright@
# @SI_Copyright@

import string
import stack.commands
from stack.exception import *

class Command(stack.commands.set.host.command):
        """
        """

	def run(self, params, args):

                (req_action, req_type) = self.fillParams([
                        ('action', None, True),
                        ('type', None, True)
                ])

		if not len(args):
                        raise ArgRequired(self, 'host')

                req_type   = req_type.lower()
		req_action = req_action.lower()
                types      = { 'os'     : 'osaction',
                               'install': 'installaction' }

                if req_type not in types.keys():
                        raise ParamValue(self, 'type', 'one of: %s' % ', '.join(types.keys()))

                exists = False
                for row in self.call('list.bootaction', [ req_action, 
                                                          'type=%s' % req_type ]):
                        exists = True
                if not exists:
                        raise CommandError(self, 'bootaction %s does not exist' % req_action)

                hosts = self.getHostnames(args)
                for host in hosts:
                        self.db.execute(
                                """
                                update nodes
                                set 
                                %s = (select id from bootnames where name='%s' and type='%s')
                                where nodes.name = '%s'
                                """ % (types[req_type], req_action, req_type, host))

                self.command('sync.host.boot', hosts)



