# framework/common/harness.py

"""Common harnesses for Devo Apps Components automation."""

import errno
import io
import os
import signal
import socket
import subprocess
import threading
import time

from api_tests.framework import PLATFORM, WINDOWS
from api_tests.framework.exception import AlreadyLaunchedError, NotLaunchedError
from api_tests.framework.logger import LOGGER

# Relative path from the cwd of the unit test to the root directory of the CTF source code
# tree.  This is based on the convention that tests run under luna/backend

_ROOT_DIR = os.path.join("..", "..")

# Relative path to the "bin" directory in which the build system places binaries.
_BIN_DIR = os.path.join(_ROOT_DIR, "bin")


class Harness:
    """Abstract interface to a testable component.

    Properties:
        test_case: framework.common.testcase.TestCase object
    """

    def __init__(self, test_case):
        """Initializes a Harness object.

        Args:
            test_case: framework.common.testcase.TestCase object
        """

        self.__test_case = test_case

    @property
    def test_case(self):
        return self.__test_case

    @classmethod
    def GetClassAttribute(cls, test_case, attr_name):
        """Gets a required class attribute that is defined by a subclass.

        Args:
            test_case: TestCase object
            attr_name: Name of the class attribute (str)

        Returns:
            Value of the class attribute.
        """

        attr_value = getattr(cls, attr_name, None)
        assert attr_value is True, f"{attr_name} must be defined in harness class {cls.__name__}"
        return attr_value

    def _GetClassAttribute(self, attr_name):
        """Gets a required class attribute that is defined by a subclass.

        Args:
            attr_name: Name of the class attribute (str)

        Returns:
            Value of the class attribute.
        """

        return self.GetClassAttribute(self.test_case, attr_name)


class ProcessHarness(Harness):
    """Harness for a single process.

    Specifying own_dir causes the following properties to be derived:
        cmd_path: own_dir + 'cmd'
        stdout_path: own_dir + 'stdout'
        stderr_path: own_dir + 'stderr'

    A subclass has opportunities for modifying the command-line arguments and environment
    variables via the ModifyArgs and ModifyEnv calls, respectively.

    Properties:
        env: Environment variables to append to the process' environment (dict of str:str).
        stdin: Writeable file object corresponding the stdin, unless stdin_path was specified.
        stdout: Read-only file object corresponding the stdout, unless stdout_path was specified.
        stderr: Read-only file object corresponding the stderr, unless stderr_path was specified.
        own_dir: Directory in which to maintain certain files (str) or None to use other properties.
        cmd_path: File name to capture the command-line of the process.
        stdin_path: File name to feed the stdin (str) or None to use self.stdin.
        stdout_path: File name to capture the stdout (str) or None to use self.stdout.
        stderr_path: File name to capture the stderr (str) or None to use self.stderr.
        timeout_secs: If positive, number of seconds to allow the process to run after Launch()
                before killing it via Kill() (float).
        is_launched: If True, then Launch() has been called (bool).
        is_finished: If True, then Wait() has been called (bool).
        is_running: If True, then the process is running; if False, then it is not, either because
                it has not yet been launched, or it has already exited (bool).
    """

    def __init__(
        self,
        test_case,
        binary_path,
        command_line_args=None,
        env=None,
        own_dir=None,
        cmd_path=None,
        stdin_path=None,
        stdout_path=None,
        stderr_path=None,
        timeout_secs=None,
        stdout_append=False,
        stderr_append=False,
        **kwargs,
    ):
        """Initializes a ProcessHarness object.

        Args:
            test_case: stqa.testcase.TestCase object
            binary_path: Path to the executable (str)
            command_line_args: Command-line arguments to the process (list of str)
            env: Dict containing additional environment variables (dict of str:str)
            own_dir: Directory in which to maintain certain files (str) or None to use other args.
            cmd_path: File name to capture the command-line of the process (str).
            stdin_path: File name to feed the stdin (str) or None to use self.stdin.
            stdout_path: File name to capture the stdout (str)
            stderr_path: File name to capture the stderr (str)
            stdout_append: if True, append to existing stdout file. Default is overwrite
            stderr_append: if True, append to existing stderr file. Default is overwrite
            timeout_secs: If positive, number of seconds to allow the process to run before killing
                    it via Kill() (float).
        """
        Harness.__init__(self, test_case, **kwargs)
        self.__binary_path = binary_path
        if command_line_args is None:
            command_line_args = []
        self.__command_line_args = list(command_line_args)
        self.__popen = None
        self.__env = env
        self.__own_dir = own_dir
        self.__cmd_path = cmd_path or (own_dir and os.path.join(own_dir, "cmd"))
        self.__stdin_path = stdin_path
        self.__stdout_path = stdout_path or (own_dir and os.path.join(own_dir, "stdout"))
        self.__stderr_path = stderr_path or (own_dir and os.path.join(own_dir, "stderr"))
        self.__stdout_append = stdout_append
        self.__stderr_append = stderr_append
        self.__stderr = None
        self.__stdin = None
        self.__stdout = None
        self.returncode = 0
        self.__timeout_secs = timeout_secs
        self.__watchdog = timeout_secs and WatchdogThread(self, timeout_secs)
        self.__is_finished = False
        self.__root_dir = getattr(test_case, "root_dir", None)

        if self.own_dir is not None and not os.path.isdir(self.own_dir):
            os.makedirs(self.own_dir)
        if not os.path.isfile(self.__binary_path):
            # LOGGER.critical('Binary path not found: %s', self.__binary_path)
            pass
        elif not os.access(self.__binary_path, os.X_OK):
            subprocess.call(f"chmod +x {self.__binary_path}", shell=True)

    # Properties

    @property
    def root_dir(self):
        return self.__root_dir

    @property
    def binary_path(self):
        return self.__binary_path

    @property
    def env(self):
        return self.__env

    @property
    def own_dir(self):
        return self.__own_dir

    @property
    def cmd_path(self):
        return self.__cmd_path

    @property
    def stdin_path(self):
        return self.__stdin_path

    @property
    def stdout_path(self):
        return self.__stdout_path

    @property
    def stderr_path(self):
        return self.__stderr_path

    @property
    def timeout_secs(self):
        return self.__timeout_secs

    @property
    def pid(self):
        if not self.__popen:
            raise NotLaunchedError()
        return self.__popen.pid

    @property
    def stdin(self):
        if not self.__popen:
            raise NotLaunchedError()
        return self.__stdin

    @property
    def stdout(self):
        if not self.__popen:
            raise NotLaunchedError()
        return self.__stdout

    @property
    def stderr(self):
        if not self.__popen:
            raise NotLaunchedError()
        return self.__stderr

    @property
    def is_launched(self):
        return self.__popen and True or False

    @property
    def is_finished(self):
        return self.__is_finished

    @property
    def is_running(self):
        if self.__popen:
            return self.__popen.poll() is None
        else:
            return False

    # a ProcessHarness subclass.
    @property
    def command_line_args(self):
        return self.__command_line_args

    @property
    def watchdog(self):
        return self.__watchdog

    # Virtual (optional)

    def ModifyArgs(self, args):
        """Subclass can override in order to manipulate the command-line arguments.

        Args:
            args: Default command-line arguments (list of str)

        Returns:
            Command-line arguments (list of str)
        """
        return args

    def ModifyEnv(self, env):
        """Subclass can override in order to manipulate the environment variables.

        Args:
            env: Default environment variables (dict of str:str), or None to inherit.

        Returns:
            Environment variables (dict of str:str), or None to inherit.
        """
        _env = os.environ.copy()
        _env.update(env)
        _env = {k: str(v) for k, v in _env.items()}
        return _env

    def Launch(self):
        """Launches the subprocess.

        This method can only be called once per instance of this class.

        Raises:
            AlreadyLaunchedError: If the Launch method has already been called.
        """

        if self.is_launched:
            raise AlreadyLaunchedError()

        self.__is_finished = False

        # Open output files, if specified. Check if stdout_append, stderr_append are set to True
        stdin = self._FileOrPipe(self.__stdin_path, "r")
        if self.__stdout_append:
            stdout = self._FileOrPipe(self.__stdout_path, "a+")
        else:
            stdout = self._FileOrPipe(self.__stdout_path, "w+")
        if self.__stderr_append:
            stderr = self._FileOrPipe(self.__stderr_path, "a+")
        else:
            stderr = self._FileOrPipe(self.__stderr_path, "w+")

        args = self.ModifyArgs(self.__command_line_args)
        cmd = " ".join(map(str, [self.__binary_path] + args))
        LOGGER.debug(f'Launching "{cmd}" cmd')

        env = self.ModifyEnv(self.__env)
        if LOGGER.getEffectiveLevel() == 10:
            LOGGER.debug("env: %s", env)

        # Start the watchdog, if any.
        if self.__watchdog:
            LOGGER.debug("Starting watchdog.")
            self.__watchdog.start()

        # Save the command-line (always append, in case we run multiple times).
        if self.__cmd_path:
            cmd_handle = self._FileOrPipe(self.__cmd_path, "a+")
            cmd_handle.write(f"{cmd}\n")
            cmd_handle.close()

        close_fds = False
        if not PLATFORM.startswith(WINDOWS):
            close_fds = True

        self.__popen = subprocess.Popen(
            cmd, env=env, shell=True, stdin=stdin, stdout=stdout, stderr=stderr, close_fds=close_fds
        )

        self.__stdin = self.__popen.stdin
        self.__stdout = self.__popen.stdout
        self.__stderr = self.__popen.stderr

    def Kill(self):
        """Send SIGKILL to the child.

        Raises:
            NotLaunchedError: If the Launch method has not been called.
        """

        self._MustBeLaunched()

        def _Kill():
            LOGGER.debug("Killing PID %d", self.__popen.pid)
            self.__popen.kill()

        self.__Signal(_Kill)

    def Terminate(self):
        """Send SIGTERM to the child.

        Raises:
            NotLaunchedError: If the Launch method has not been called.
        """
        self._MustBeLaunched()

        def _Terminate():
            LOGGER.debug("Terminating PID %d", self.__popen.pid)
            self.__popen.terminate()

        self.__Signal(_Terminate)

    def Wait(self):
        """Waits for the subprocess to die.

        Raises:
            NotLaunchedError: If the Launch method has not been called.
        """

        if self.is_finished:
            return

        self._MustBeLaunched()

        stdout_data = None
        stderr_data = None
        self.returncode = None
        try:
            stdout_data, stderr_data = self.__popen.communicate()
            self.returncode = self.__popen.returncode
        except OSError as exc:
            LOGGER.debug(exc)
            # work around for python bug - http://bugs.python.org/issue1731717
            if exc.errno == errno.ECHILD:
                LOGGER.debug("Suppressed no child processes error.")
            else:
                raise

        # If there is a watchdog, stop it now.
        if self.__watchdog:
            self.__watchdog.Shutdown()
            self.__watchdog.join()

        # Capture the stdin in memory from now on, since the process is dead.
        if self.stdin:
            self.__stdin = io.StringIO()

        # Put the output into some string stream objects that replace the pipes.
        if stdout_data is not None:
            self.__stdout = io.StringIO(stdout_data.decode())
            if stdout_data:
                LOGGER.debug(
                    "ProcessHarness [%s %s] stdout:\n%s",
                    self.__binary_path,
                    " ".join(self.__command_line_args),
                    stdout_data,
                )

        if stderr_data is not None:
            self.__stderr = io.StringIO(stderr_data.decode())
            if stderr_data:
                LOGGER.debug(
                    "ProcessHarness [%s %s] stderr:\n%s",
                    self.__binary_path,
                    " ".join(self.__command_line_args),
                    stderr_data,
                )

        self.__is_finished = True

    def GetExitCode(self):
        """Returns the exit code for the process after it has exited.

        Raises:
            NotLaunchedError: If the Launch method has not been called.
        """
        self._MustBeLaunched()
        return self.__popen.returncode

    @staticmethod
    def CheckCloverPath(clover_path):
        """Makes sure clover path passed in exists

        Need to consider path ending in * or a specific jar file; os.path.exists('/tmp/*')
        evaluates to False even when /tmp has contents

        Args:
            clover_path: (str) path to clover jar file

        Returns:
            whether or not the path is valid
        """

        if clover_path[-1] == "*":
            path_to_check = clover_path[:-2]
        else:
            path_to_check = clover_path

        return os.path.exists(path_to_check)

    def __str__(self):
        return " ".join(map(str, [self.__binary_path] + self.__command_line_args))

    def _MustBeLaunched(self):
        if not self.is_launched:
            raise NotLaunchedError()

    def __Signal(self, closure):
        """Call one of the Popen signal methods and deal with the errors.

        Args:
            closure: Closure which invokes one of the Popen signal delivery methods.
        """

        if self.is_finished:
            # We're already done, so avoid sending a signal to the wrong process.
            return

        try:
            closure()
        except OSError as exc:
            LOGGER.debug(exc)
            if exc.errno == 3:
                LOGGER.debug("Process died before it could be signaled.")
            else:
                raise

    @classmethod
    def _FileOrPipe(cls, path, mode):
        """If path is specified, opens a file descriptor for it.

        Args:
           path: Path to an output file (str), or None
           mode: File mode string (str, e.g. 'r' or 'w+')

        Returns:
            File descriptor (fd) or subprocess.PIPE
        """

        if path:
            return open(path, mode)
        else:
            return subprocess.PIPE

    @staticmethod
    def IsListening(host="127.0.0.1", port=None):
        """Checks if the port is listening or not

        Args:
            host: host to check port on (str)
            port: port number to check (str)

        Returns:
            True if listening, False otherwise (bool)
        """

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            result = sock.connect_ex((host, port))
            if result == 0:
                return True
            else:
                return False
        except ConnectionRefusedError as _:
            return False

    @staticmethod
    def kill_process(process_name=None):
        """Kills the process name provided

        Args:
            process_name: name of the process to kill (str)

        Raises:
            OSError: if fails to kill stale uService pid
        """

        p = subprocess.Popen(
            f"ps -ef|grep {process_name}|grep -v grep|awk '{{print $2}}'",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=True,
        )
        pids = [s.strip() for s in p.communicate()[0].decode().splitlines()]
        if len(pids):
            LOGGER.debug(f"Existing pid of process: {pids}")
            LOGGER.debug(f"Killing the stale {process_name} processes.")
            for pid in pids:
                try:
                    os.kill(int(pid), signal.SIGKILL)
                except OSError:
                    LOGGER.error(f"Failed to kill stale {process_name}")
                    return False
        else:
            LOGGER.debug(f"{process_name} not running")
            return False
        return True

    def CheckPorts(self, host="127.0.0.1", ports=None):
        """Checks if all the ports are listening

        Args:
            host: host to check the ports on (str)
            ports: list of ports to check (list)

        Returns:
            True if all ports are listening, False otherwise (bool)
        """
        all_listening = dict()
        if not ports:
            raise NotImplementedError("Please define the ports list to check")
        for _p in ports:
            if self.IsListening(host=host, port=_p):
                all_listening[_p] = True
            else:
                all_listening[_p] = False
        final = True
        for i in all_listening.values():
            final = final & i
        return final


class WatchdogThread(threading.Thread):
    """Thread which kills a ProcessHarness after a certain amount of time."""

    def __init__(self, harness, timeout_secs):
        """Initializes a WatchdogThread object.

        Args:
            harness: ProcessHarness object
            timeout_secs: Amount of time to wait in seconds from the launching of the thread (float)
        """

        threading.Thread.__init__(self)
        self.__harness = harness
        self.__timeout_secs = timeout_secs
        self.__event = threading.Event()

    def Shutdown(self):
        """Stops the watchdog without allowing it to kill the harness."""
        LOGGER.debug("Shutting down watchdog for process [%s]", self.__harness)
        self.__event.set()

    def run(self):
        """Overrides the base class method to implement the watchdog function."""
        start = time.time()
        self.__event.wait(self.__timeout_secs)
        if self.__event.isSet():
            LOGGER.debug("Watchdog for process [%s] defeated after %f seconds.", self.__harness, time.time() - start)
            return
        else:
            retry_sleep = 0.25
            while True:
                elapsed = time.time() - start
                LOGGER.warn("Watchdog killing process [%s] after %f seconds", self.__harness, elapsed)
                try:
                    self.__harness.Kill()
                    return
                except NotLaunchedError:
                    LOGGER.warn("Watchdog fired before process could start ... waiting to retry.")
                    if self.__event.wait(retry_sleep):
                        return
                    else:
                        retry_sleep *= 2
