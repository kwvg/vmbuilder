#
#    Uncomplicated VM Builder
#    Copyright (C) 2007-2009 Canonical Ltd.
#    
#    See AUTHORS for list of contributors
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License version 3, as
#    published by the Free Software Foundation.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
from VMBuilder import register_distro_plugin, Plugin, VMBuilderUserError

import logging
import os

class Firstscripts(Plugin):
    """
    Plugin to provide --firstboot and --firstlogin scripts capabilities
    """
    name = 'First-Scripts plugin'

    def register_options(self):
        group = self.context.setting_group('Scripts')
        group.add_option('--firstboot', metavar='PATH', default='', help='Specify a script that will be copied into the guest and executed the first time the machine boots.  This script must not be interactive.')
        group.add_option('--firstlogin', metavar='PATH', default='', help='Specify a script that will be copied into the guest and will be executed the first time the user logs in. This script can be interactive.')
        self.context.register_setting_group(group)

    def preflight_check(self):
        
        if self.context.firstboot:
            logging.debug("Checking if firstboot script %s exists" % (self.context.firstboot,))
            if not(os.path.isfile(self.context.firstboot)):
                raise VMBuilderUserError('The path to the first-boot script is invalid: %s. Make sure you are providing a full path.' % self.context.firstboot)
                
        if self.context.firstlogin:
            logging.debug("Checking if first login script %s exists" % (self.context.firstlogin,))
            if not(os.path.isfile(self.context.firstlogin)):
                raise VMBuilderUserError('The path to the first-login script is invalid: %s.  Make sure you are providing a full path.' % self.context.firstlogin)

    def post_install(self):
        logging.debug("Installing firstboot script %s" % (self.context.firstboot,))
        if self.context.firstboot:
            self.context.install_file('/root/firstboot.sh', source=self.vm.firstboot, mode=0700)
            os.rename('%s/etc/rc.local' % self.context.installdir, '%s/etc/rc.local.orig' % self.vm.installdir)
            self.install_from_template('/etc/rc.local', 'firstbootrc', mode=0755)

        logging.debug("Installing first login script %s" % (self.context.firstlogin,))
        if self.context.firstlogin:
            self.context.install_file('/root/firstlogin.sh', source=self.vm.firstlogin, mode=0755)
            os.rename('%s/etc/bash.bashrc' % self.context.installdir, '%s/etc/bash.bashrc.orig' % self.vm.installdir)
            self.install_from_template('/etc/bash.bashrc', 'firstloginrc')

        return True

#register_plugin(Firstscripts)
