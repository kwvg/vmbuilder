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
#    Various utility functions
import errno
import logging
import os
import os.path
import select
import subprocess
import tempfile
from   exception        import VMBuilderException, VMBuilderUserError

class NonBufferedFile():
    def __init__(self, file):
        self.file = file
        self.buf = ''

    def __getattr__(self, attr):
        if attr == 'closed':
            return self.file.closed
        else:
            raise AttributeError()

    def __iter__(self):
        return self

    def read_will_block(self):
        (ins, foo, bar) = select.select([self.file], [], [], 1)

        if self.file not in ins:
            return True
        return False

    def next(self):
        if self.file.closed:
            raise StopIteration()

        while not self.read_will_block():
            c = self.file.read(1)
            if not c:
                self.file.close()
                if self.buf:
                    return self.buf
                else:
                    raise StopIteration
            else:
                self.buf += c
            if self.buf.endswith('\n'):
                ret = self.buf
                self.buf = ''
                return ret
        raise StopIteration()
    
def run_cmd(*argv, **kwargs):
    """
    Runs a command.

    Locale is reset to C to make parsing error messages possible.

    @type  stdin: string
    @param stdin: input to provide to the process on stdin. If None, process'
                  stdin will be attached to /dev/null
    @type  ignore_fail: boolean
    @param ignore_fail: If True, a non-zero exit code from the command will not 
                        cause an exception to be raised.
    @type  env: dict
    @param env: Dictionary of extra environment variables to set in the new process

    @rtype:  string
    @return: string containing the stdout of the process
    """

    env = kwargs.get('env', {})
    stdin = kwargs.get('stdin', None)
    ignore_fail = kwargs.get('ignore_fail', False)
    stdout = stderr = ''
    args = [str(arg) for arg in argv]
    logging.debug(args.__repr__())
    if stdin:
        logging.debug('stdin was set and it was a string: %s' % (stdin,))
        stdin_arg = subprocess.PIPE
    else:
        stdin_arg = file('/dev/null', 'r')
    proc_env = dict(os.environ)
    proc_env['LANG'] = 'C'
    proc_env['LC_ALL'] = 'C'
    proc_env.update(env)

    try:
        proc = subprocess.Popen(args, stdin=stdin_arg, stderr=subprocess.PIPE, stdout=subprocess.PIPE, env=proc_env)
    except OSError, error:
        if error.errno == errno.ENOENT:
            raise VMBuilderUserError, "Couldn't find the program '%s' on your system" % (argv[0])
        else:
            raise VMBuilderUserError, "Couldn't launch the program '%s': %s" % (argv[0], error)

    if stdin:
        proc.stdin.write(stdin)
        proc.stdin.close()

    mystdout = NonBufferedFile(proc.stdout)
    mystderr = NonBufferedFile(proc.stderr)

    while not (mystdout.closed and mystderr.closed):
        # Block until either of them has something to offer
        select.select([x.file for x in [mystdout, mystderr] if not x.closed], [], [])
        for buf in mystderr:
            stderr += buf
            (ignore_fail and logging.debug or logging.info)(buf.rstrip())

        for buf in mystdout:
            logging.debug(buf.rstrip())
            stdout += buf

    status = proc.wait()
    if not ignore_fail and status != 0:
        raise VMBuilderException, "Process (%s) returned %d. stdout: %s, stderr: %s" % (args.__repr__(), status, stdout, stderr)
    return stdout

def checkroot():
    """
    Check if we're running as root, and bail out if we're not.
    """

    if os.geteuid() != 0:
        raise VMBuilderUserError("This script must be run as root (e.g. via sudo)")

def render_template(plugin, vm, tmplname, context=None):
    # Import here to avoid having to build-dep on python-cheetah
    from   Cheetah.Template import Template
    searchList = []
    if context:
        searchList.append(context)
    searchList.append(vm)

    tmpldirs = [os.path.expanduser('~/.vmbuilder/%s'),
                os.path.dirname(__file__) + '/plugins/%s/templates',
                '/etc/vmbuilder/%s']

#    if vm.templates:
#        tmpldirs.insert(0,'%s/%%s' % vm.templates)
    
    tmpldirs = [dir % plugin for dir in tmpldirs]

    for dir in tmpldirs:
        tmplfile = '%s/%s.tmpl' % (dir, tmplname)
        if os.path.exists(tmplfile):
            t = Template(file=tmplfile, searchList=searchList)
            output = t.respond()
            logging.debug('Output from template \'%s\': %s' % (tmplfile, output))
            return output

    raise VMBuilderException('Template %s.tmpl not found in any of %s' % (tmplname, ', '.join(tmpldirs)))

def call_hooks(context, func, *args, **kwargs):
    logging.debug('Calling hook: %s(args=%r, kwargs=%r)' % (func, args, kwargs))
    for plugin in context.plugins:
        logging.debug('Calling %s method in %s plugin.' % (func, plugin.__module__))
        getattr(plugin, func, log_no_such_method)(*args, **kwargs)

    for f in context.hooks.get(func, []):
        logging.debug('Calling %r.' % (f,))
        f(*args, **kwargs)

    logging.debug('Calling %s method in context plugin %s.' % (func, context.__module__))
    getattr(context, func, log_no_such_method)(*args, **kwargs)

def log_no_such_method(*args, **kwargs):
    logging.debug('No such method')
    return

def tmpfile(suffix='', keep=True):
    (fd, filename) = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    if not keep:
        os.unlink(filename)
    return filename

def tmpdir(suffix='', keep=True):
    dir = tempfile.mkdtemp(suffix=suffix)
    if not keep:
        os.rmdir(dir)
    return dir

