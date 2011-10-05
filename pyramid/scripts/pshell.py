from code import interact
import optparse
import os
import sys
from logging.config import fileConfig

from pyramid.compat import configparser
from pyramid.util import DottedNameResolver
from pyramid.paster import bootstrap

def main(argv=sys.argv):
    command = PShellCommand(argv)
    return command.run()

class PShellCommand(object):
    """Open an interactive shell with a :app:`Pyramid` app loaded.

    This command accepts one positional argument:

    ``config_uri`` -- specifies the PasteDeploy config file to use for the
    interactive shell. The format is ``inifile#name``. If the name is left
    off, ``main`` will be assumed.

    Example::

        $ pshell myapp.ini#main

    .. note:: If you do not point the loader directly at the section of the
              ini file containing your :app:`Pyramid` application, the
              command will attempt to find the app for you. If you are
              loading a pipeline that contains more than one :app:`Pyramid`
              application within it, the loader will use the last one.

    """
    bootstrap = (bootstrap,) # for testing
    summary = "Open an interactive shell with a Pyramid application loaded"

    min_args = 1
    max_args = 1

    parser = optparse.OptionParser()
    parser.add_option('-d', '--disable-ipython',
                      action='store_true',
                      dest='disable_ipython',
                      help="Don't use IPython even if it is available")
    parser.add_option('--setup',
                      dest='setup',
                      help=("A callable that will be passed the environment "
                            "before it is made available to the shell. This "
                            "option will override the 'setup' key in the "
                            "[pshell] ini section."))

    ConfigParser = configparser.ConfigParser # testing

    loaded_objects = {}
    object_help = {}
    setup = None

    def __init__(self, argv):
        self.options, self.args = self.parser.parse_args(argv[1:])

    def pshell_file_config(self, filename):
        config = self.ConfigParser()
        config.read(filename)
        try:
            items = config.items('pshell')
        except configparser.NoSectionError:
            return

        resolver = DottedNameResolver(None)
        self.loaded_objects = {}
        self.object_help = {}
        self.setup = None
        for k, v in items:
            if k == 'setup':
                self.setup = v
            else:
                self.loaded_objects[k] = resolver.maybe_resolve(v)
                self.object_help[k] = v

    def run(self, shell=None):
        config_uri = self.args[0]
        config_file = config_uri.split('#', 1)[0]
        self.logging_file_config(config_file)
        self.pshell_file_config(config_file)

        # bootstrap the environ
        env = self.bootstrap[0](config_uri)

        # remove the closer from the env
        closer = env.pop('closer')

        # setup help text for default environment
        env_help = dict(env)
        env_help['app'] = 'The WSGI application.'
        env_help['root'] = 'Root of the default resource tree.'
        env_help['registry'] = 'Active Pyramid registry.'
        env_help['request'] = 'Active request object.'
        env_help['root_factory'] = (
            'Default root factory used to create `root`.')

        # override use_script with command-line options
        if self.options.setup:
            self.setup = self.options.setup

        if self.setup:
            # store the env before muddling it with the script
            orig_env = env.copy()

            # call the setup callable
            resolver = DottedNameResolver(None)
            setup = resolver.maybe_resolve(self.setup)
            setup(env)

            # remove any objects from default help that were overidden
            for k, v in env.iteritems():
                if k not in orig_env or env[k] != orig_env[k]:
                    env_help[k] = v

        # load the pshell section of the ini file
        env.update(self.loaded_objects)

        # eliminate duplicates from env, allowing custom vars to override
        for k in self.loaded_objects:
            if k in env_help:
                del env_help[k]

        # generate help text
        help = ''
        if env_help:
            help += 'Environment:'
            for var in sorted(env_help.keys()):
                help += '\n  %-12s %s' % (var, env_help[var])

        if self.object_help:
            help += '\n\nCustom Variables:'
            for var in sorted(self.object_help.keys()):
                help += '\n  %-12s %s' % (var, self.object_help[var])

        if shell is None and not self.options.disable_ipython:
            shell = self.make_ipython_v0_11_shell()
            if shell is None:
                shell = self.make_ipython_v0_10_shell()

        if shell is None:
            shell = self.make_default_shell()

        try:
            shell(env, help)
        finally:
            closer()

    def make_default_shell(self, interact=interact):
        def shell(env, help):
            cprt = 'Type "help" for more information.'
            banner = "Python %s on %s\n%s" % (sys.version, sys.platform, cprt)
            banner += '\n\n' + help + '\n'
            interact(banner, local=env)
        return shell

    def make_ipython_v0_11_shell(self, IPShellFactory=None):
        if IPShellFactory is None: # pragma: no cover
            try:
                from IPython.frontend.terminal.embed import (
                    InteractiveShellEmbed)
                IPShellFactory = InteractiveShellEmbed
            except ImportError:
                return None
        def shell(env, help):
            IPShell = IPShellFactory(banner2=help + '\n', user_ns=env)
            IPShell()
        return shell

    def make_ipython_v0_10_shell(self, IPShellFactory=None):
        if IPShellFactory is None: # pragma: no cover
            try:
                from IPython.Shell import IPShellEmbed
                IPShellFactory = IPShellEmbed
            except ImportError:
                return None
        def shell(env, help):
            IPShell = IPShellFactory(argv=[], user_ns=env)
            IPShell.set_banner(IPShell.IP.BANNER + '\n' + help + '\n')
            IPShell()
        return shell

    def logging_file_config(self, config_file):
        """
        Setup logging via the logging module's fileConfig function with the
        specified ``config_file``, if applicable.

        ConfigParser defaults are specified for the special ``__file__``
        and ``here`` variables, similar to PasteDeploy config loading.
        """
        parser = configparser.ConfigParser()
        parser.read([config_file])
        if parser.has_section('loggers'):
            config_file = os.path.abspath(config_file)
            fileConfig(config_file, dict(__file__=config_file,
                                         here=os.path.dirname(config_file)))
