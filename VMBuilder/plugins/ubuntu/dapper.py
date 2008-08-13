#
#    Uncomplicated VM Builder
#    Copyright (C) 2007-2008 Canonical
#    
#    See AUTHORS for list of contributors
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
import glob
import logging
import os
import stat
import suite
import VMBuilder.disk as disk
from   VMBuilder.util import run_cmd

class Dapper(suite.Suite):
    updategrub = "/sbin/update-grub"
    grubroot = "/lib/grub"
    valid_flavours = { 'i386' :  ['386', '686', '686-smp', 'k7', 'k7-smp', 'server', 'server-bigiron'],
                       'amd64' : ['amd64-generic', 'amd64-k8', 'amd64-k8-smp', 'amd64-server', 'amd64-xeon']}
    default_flavour = { 'i386' : 'server', 'amd64' : 'amd64-server' }
    disk_prefix = 'hd'

    def check_kernel_flavour(self, arch, flavour):
        return flavour in self.valid_flavours[arch]

    def install(self, destdir):
        self.destdir = destdir

        logging.debug("debootstrapping")
        self.debootstrap()

        logging.debug("Installing fstab")
        self.install_fstab()
    
        if self.vm.hypervisor.needs_bootloader:
            logging.debug("Installing grub")
            self.install_grub()
        
        logging.debug("Configuring guest networking")
        self.config_network()

        if self.vm.hypervisor.needs_bootloader:
            logging.debug("Installing menu.list")
            self.install_menu_lst()
        
        logging.debug("Preventing daemons from starting")
        self.prevent_daemons_starting()

        if self.vm.hypervisor.needs_bootloader:
            logging.debug("Installing kernel")
            self.install_kernel()

        if self.vm.hypervisor.needs_bootloader:
            logging.debug("Creating device.map")
            self.install_device_map()

        logging.debug("Installing extra packages")
        self.install_extras()

        logging.debug("Unmounting volatile lrm filesystems")
        self.unmount_volatile()

        logging.debug("Unpreventing daemons from starting")
        self.unprevent_daemons_starting()

    def kernel_name(self):
        return 'linux-image-%s' % (self.vm.flavour or self.default_flavour[self.vm.arch],)

    def config_network(self):
        self.install_file('/etc/hostname', self.vm.hostname)
        self.install_file('/etc/hosts', '''127.0.0.1 localhost
127.0.1.1 %s.%s %s

# The following lines are desirable for IPv6 capable hosts
::1 ip6-localhost ip6-loopback
fe00::0 ip6-localnet
ff00::0 ip6-mcastprefix
ff02::1 ip6-allnodes
ff02::2 ip6-allrouters
ff02::3 ip6-allhosts''' % (self.vm.hostname, self.vm.domain, self.vm.hostname))

    def unprevent_daemons_starting(self):
        os.unlink('%s/usr/sbin/policy-rc.d' % self.destdir)

    def prevent_daemons_starting(self):
        path = '%s/usr/sbin/policy-rc.d' % self.destdir
        fp  = open(path, 'w')
        fp.write("""#!/bin/sh

while true; do
    case "$1" in
        -*)
            shift
            ;;
        makedev)
            exit 0
            ;;
        x11-common)
            exit 0
            ;;
        *)
            exit 101
            ;;
    esac
done
""")
        os.chmod(path, 0755)

    def install_extras(self):
        if not self.vm.addpkg and not self.vm.removepkg:
            return
        cmd = ['chroot', self.destdir, 'apt-get', 'install', '-y', '--force-yes']
        cmd += self.vm.addpkg or []
        cmd += ['%s-' % pkg for pkg in self.vm.removepkg or []]
#       logging.debug(cmd.__repr__())
#       import os, signal
#       os.kill(os.getpid(), signal.SIGSTOP)
        run_cmd(*cmd)
        
    def unmount_volatile(self):
        for mntpnt in glob.glob('%s/lib/modules/*/volatile' % self.destdir):
            logging.debug("Unmounting %s" % mntpnt)
            run_cmd('umount', mntpnt)

    def install_menu_lst(self):
        run_cmd('mount', '--bind', '/dev', '%s/dev' % self.destdir)
        self.vm.add_clean_cmd('umount', '%s/dev' % self.destdir, ignore_fail=True)

        self.run_in_target('mount', '-t', 'proc', 'proc', '/proc')
        self.vm.add_clean_cmd('umount', '%s/proc' % self.destdir, ignore_fail=True)

        self.run_in_target(self.updategrub, '-y')
        self.mangle_grub_menu_lst()
        self.run_in_target(self.updategrub)
        self.run_in_target('grub-set-default', '0')

        run_cmd('umount', '%s/dev' % self.destdir)
        run_cmd('umount', '%s/proc' % self.destdir)

    def mangle_grub_menu_lst(self):
        bootdev = disk.bootpart(self.vm.disks)
        run_cmd('sed', '-ie', 's/^# kopt=root=\([^ ]*\)\(.*\)/# kopt=root=\/dev\/hd%s%d\\2/g' % (bootdev.disk.devletters, bootdev.get_index()+1), '%s/boot/grub/menu.lst' % self.destdir)
        run_cmd('sed', '-ie', 's/^# groot.*/# groot %s/g' % bootdev.get_grub_id(), '%s/boot/grub/menu.lst' % self.destdir)
        run_cmd('sed', '-ie', '/^# kopt_2_6/ d', '%s/boot/grub/menu.lst' % self.destdir)

    def install_fstab(self):
        self.install_file('/etc/fstab', self.fstab())

    def install_device_map(self):
        self.install_file('/boot/grub/device.map', self.device_map())

    def device_map(self):
        return '\n'.join(['(%s) /dev/%s%s' % (self.disk_prefix, disk.get_grub_id(), disk.devletters) for disk in self.vm.disks])

    def debootstrap(self):
        cmd = ['/usr/sbin/debootstrap', self.vm.suite, self.destdir]
        if self.vm.mirror:
            cmd += [self.vm.mirror]
        run_cmd(*cmd)

    def install_kernel(self):
        self.install_file('/etc/kernel-img.conf', ''' 
do_symlinks = yes
relative_links = yes
do_bootfloppy = no
do_initrd = yes
link_in_boot = no
postinst_hook = %s
postrm_hook = %s
do_bootloader = no''' % (self.updategrub, self.updategrub))
        run_cmd('chroot', self.destdir, 'apt-get', '--force-yes', '-y', 'install', self.kernel_name(), 'grub')

    def install_grub(self):
        self.run_in_target('apt-get', '--force-yes', '-y', 'install', 'grub')
        run_cmd('cp', '-a', '%s%s/%s/' % (self.destdir, self.grubroot, self.vm.arch == 'amd64' and 'x86_64-pc' or 'i386-pc'), '%s/boot/grub' % self.destdir) 

    def fstab(self):
        retval = '''# /etc/fstab: static file system information.
#
# <file system>                                 <mount point>   <type>  <options>       <dump>  <pass>
proc                                            /proc           proc    defaults        0       0
'''
        parts = disk.get_ordered_partitions(self.vm.disks)
        for part in parts:
            retval += "/dev/%s%-38s %15s %7s %15s %d       %d\n" % (self.disk_prefix, part.get_suffix(), part.mntpnt, part.fstab_fstype(), part.fstab_options(), 0, 0)
        return retval

    def install_file(self, path, contents):
        fp = open('%s%s' % (self.destdir, path), 'w')
        fp.write(contents)
        fp.close()

    def run_in_target(self, *args, **kwargs):
        return run_cmd('chroot', self.destdir, *args, **kwargs)

