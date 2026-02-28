# artemis/framework/common/testcase.py

"""Common test case for Devo Apps automation."""

import os
import sys

from faker import Faker

from api_tests.framework import PATH_SEPARATOR, common_unittest
from api_tests.framework.logger import LOGGER, LogStream


class TestCase(common_unittest.TestCase):
    """Container (case) of tests.

    Compatible with the Python unittest.TestCase.

    Any sub-class inheriting from this Class, should have TestCase as the first Inheritance class
    to ensure correct Member Class Resolution. See ESAServerWithRabbitMQTestCase Class for example.

    Properties (available after setUp):
        test_module_name: Name of the test module running this test.
        test_class_name: Name of the test case class.
        test_case_name: Name of the test within the test case.
        test_id: Fully qualified name of the test (within this test binary).

        test_module_td_dir: Subdirectory containing read-only test data for the entire suite.
        test_class_td_dir: Subdirectory containing read-only test data unique to the test class.
        test_case_td_dir: Subdirectory containing read-only test data unique to the test case.
        test_td_dir: Subdirectory containing read-only test data unique to the test.

        test_module_kg_dir: Subdirectory containing known-goods for the entire suite.
        test_class_kg_dir: Subdirectory containing known-goods unique to the test class.
        test_case_kg_dir: Subdirectory containing known-goods unique to the test case.
        test_case_kg_file: known-goods unique to the test case.

        test_module_o_dir: Subdirectory containing output for all tests for the entire suite.
        test_class_o_dir: Subdirectory containing output unique to the test class.
        test_case_o_dir: Subdirectory containing output unique to the test case.
        test_o_dir: Subdirectory containing output unique to the test.
        test_log_path: File that captures the log messages from the test.
    """

    @property
    def test_id(self):
        return self.__test_id

    @property
    def test_component(self):
        return self.__test_component

    @property
    def test_dir(self):
        return self.__test_dir

    @property
    def test_module_name(self):
        return self.__test_module_name

    @property
    def test_class_name(self):
        return self.__test_class_name

    @property
    def test_case_name(self):
        return self.__test_case_name

    @property
    def testdata_dir(self):
        return "testdata"

    @property
    def test_td_dir(self):
        return self.__test_td_dir

    @property
    def test_module_td_dir(self):
        return self.__test_module_td_dir

    @property
    def test_class_td_dir(self):
        return self.__test_class_td_dir

    @property
    def test_case_td_dir(self):
        return self.__test_case_td_dir

    @property
    def knowngood_dir(self):
        return "knowngood"

    @property
    def test_kg_dir(self):
        return self.__test_kg_dir

    @property
    def test_module_kg_dir(self):
        return self.__test_module_kg_dir

    @property
    def test_class_kg_dir(self):
        return self.__test_class_kg_dir

    @property
    def test_case_kg_dir(self):
        return self.__test_case_kg_dir

    @property
    def output_dir(self):
        return "o"

    @property
    def test_o_dir(self):
        return self.__test_o_dir

    @property
    def test_module_o_dir(self):
        return self.__test_module_o_dir

    @property
    def test_class_o_dir(self):
        return self.__test_class_o_dir

    @property
    def test_case_o_dir(self):
        return self.__test_case_o_dir

    @property
    def test_log_path(self):
        return self.__test_log_path

    @property
    def root_dir(self):
        return self.__root_dir

    @property
    def test_qc_data(self):
        return self.__test_qc_data

    @property
    def faker(self):
        return Faker(locale=os.environ.get("ARTEMIS_FAKER_LOCALE", "en-US"))

    def GenericAsserts(self):
        """Override this to perform asserts on each test.

        This hook allows the use of mix-in classes to define groups of reusable asserts.  It
        requires you chain to the other mix-in classes using super as follows:

            super(YourTestCase, self).GenericAsserts()
        """
        pass

    def setUp(self):
        """Override this to do per-test initialization.  Always chain back to this method."""

        super().setUp()
        self.__test_id = self.id()
        id_list = self.test_id.split(".")
        self.__test_case_name = id_list.pop()
        self.__test_class_name = id_list.pop()
        test_module = id_list.pop()
        self.__test_module_name = f"{test_module}.py"
        self.__test_dir = os.path.dirname(sys.modules[self.__class__.__module__].__file__)
        test_dir_path_list = self.test_dir.split(PATH_SEPARATOR)
        self.__test_component = PATH_SEPARATOR.join(test_dir_path_list[:-1])
        self.__root_dir = PATH_SEPARATOR.join(test_dir_path_list[:-5])

        # Generate test testdata details
        self.__test_td_dir = os.path.join(self.test_component, self.testdata_dir)
        self.__test_module_td_dir = os.path.join(self.test_td_dir, self.test_module_name)
        self.__test_class_td_dir = os.path.join(self.test_module_td_dir, self.test_class_name)
        self.__test_case_td_dir = os.path.join(self.test_class_td_dir, self.test_case_name)

        # Generate test knowngoods details
        self.__test_module_kg_dir = os.path.join(self.test_module_td_dir, self.knowngood_dir)
        self.__test_class_kg_dir = os.path.join(self.test_class_td_dir, self.knowngood_dir)
        self.__test_case_kg_dir = os.path.join(self.test_case_td_dir, self.knowngood_dir)

        # Generate test output details
        self.__test_o_dir = os.path.join(self.test_component, self.output_dir)
        self.__test_module_o_dir = os.path.join(self.test_o_dir, self.test_module_name)
        self.__test_class_o_dir = os.path.join(self.test_module_o_dir, self.test_class_name)
        self.__test_case_o_dir = os.path.join(self.test_class_o_dir, self.test_case_name)

        self.__test_log_path = os.path.join(self.test_case_o_dir, "test.log")

        # Start with an empty test_out_dir.
        _RecreateDir(self.test_case_o_dir)

        # Capture all log output in a file.
        self.__test_log_id = LogStream.Register(open(self.test_log_path, "w+"))
        LOGGER.name = self.test_module_name

    def tearDown(self):
        """Override this to do per-test clean-up.  Always chain back to this method."""
        # Run the generic asserts.
        self.GenericAsserts()

        common_unittest.TestCase.tearDown(self)

        # Stop capturing log output.
        LogStream.Unregister(self.__test_log_id)

    def shortDescription(self):
        """Override this so when nose prints out test result, test name will be included."""

        return str(self) + " " + super().shortDescription()

    def _GetClassAttribute(self, attr_name):
        """Gets a required class attribute that is provided in a base class.

        Args:
            attr_name: Name of the class attribute (str)

        Returns:
            Value of the class attribute.
        """
        attr_value = getattr(self, attr_name, None)
        self.assertTrue(
            attr_value,
            f"{attr_name} must be defined in test case {self.test_class_name} in test binary {self.test_module_name}",
        )
        return attr_value

    def RunTestCaseSpecificSetup(self):
        """Calls the test case specific setup method

        Note:
            The test case specific method must follow a naming convention for it to be picked up.
            setUp_<test_case_name> (test case name after the first '_')
            Example: For a test case named - 'test_basic_rule' the test case specific setup method
            should be named 'setUp_basic_rule' for it to be picked up.

        Usage:
            Call this method at the end of the Test Class setUp:
            self.RunTestCaseSpecificSetup()
        """
        # Determines the setUp method name
        try:
            test_case_setup = f"setUp_{self.test_case_name.split('_', 1)[1]}"
        except IndexError:
            # Handles case where a test case name does not contain an underscore
            pass
        else:
            if hasattr(self, test_case_setup):
                getattr(self, test_case_setup)()

    def RunTestCaseSpecificTearDown(self):
        """Calls the test case specific tearDown method

        Note:
            The test case specific method must follow a naming convention for it to be picked up.
            tearDown_<test_case_name> (test case name after the first '_')
            Example: For a test case named - 'test_basic_rule' the test case specific setup method
            should be named 'tearDown_basic_rule' for it to be picked up.

        Usage:
            Call this method at the end of the Test Class tearDown:
            self.RunTestCaseSpecificTearDown()
        """
        # Determines the tearDown method name
        try:
            test_case_teardown = f"tearDown_{self.test_case_name.split('_', 1)[1]}"
        except IndexError:
            # Handles case where a test case name does not contain an underscore
            pass
        else:
            if hasattr(self, test_case_teardown):
                getattr(self, test_case_teardown)()


def _RecreateDir(path):
    """Creates an empty subdirectory if it doesn't already exist."""
    os.makedirs(path, exist_ok=True)


class AbstractComponentTestCase(TestCase):
    """Tests that focus on a single instance of a single production binary.

    Virtual properties must be defined, typically at the class level.

    HARNESS_FACTORY: Factory (typically a class object) that produces harness.ServiceHarness.
    TIMEOUT_SECS: Number of seconds to allow the component to run.

    A test has opportunities to modify the environment variables of the component.  By default, the
    environment of the test will be inherited.

    (1) The test case can override the ModifyEnv method.  It may or may not choose to call the
        superclass method to incorporate those arguments.

    (2) A method named ModifyEnv_test_foo, if present, will be invoked during setUp of test_foo.
        It should have the same signature as ModifyEnv.

    Properties (available after setUp):
        binary_path: Path to the binary (executable) to be tested (str).
        service_conf: Conf object generated for this service.
        xml_conf_path: Path to the XML rendering of the universal conf file (str).
        args: Command-line arguments used to launch the component (list of str).
        env: Environment variables for the component (dict of str:str).
        stdout_path: File path capturing the stdout stream of the component (str)
        stderr_path: File path capturing the stderr stream of the component (str)
        harness: Harness for the component (harness.ServiceHarness object)
    """

    # (The virtual properties are not defined here in order to allow mix-in classes to specify
    # them.)

    # Properties:

    @property
    def binary_path(self):
        return self.harness.binary_path

    @property
    def env(self):
        return self.__env

    @env.setter
    def env(self, value):
        self.__env = value

    @property
    def stdout_path(self):
        return self.harness.stdout_path

    @property
    def stderr_path(self):
        return self.harness.stderr_path

    def __get_harness(self):
        return self.__harness

    def __set_harness(self, new_harness):
        self.__harness = new_harness

    def __delete_harness(self):
        del self.__harness

    harness = property(__get_harness, __set_harness, __delete_harness)

    # Optional to override:

    def ModifyEnv(self, env):
        """Returns the environment variables for executing the component.

        Args:
            env: Default environment variables (dict of str:str)

        Returns:
            Default environment variables to use for this test case (dict of str:str)
        """
        return env

    def setUp(self):
        TestCase.setUp(self)

        # Build the harness.
        harness_factory = self._GetClassAttribute("HARNESS_FACTORY")

        # Determine the environment variables for the component.
        self.__env = self.__GetEnv()

        self.__harness = harness_factory(
            self, env=self.env, own_dir=self.test_case_o_dir, timeout_secs=self.TIMEOUT_SECS
        )

    def tearDown(self, kill_harness=True):
        TestCase.tearDown(self)
        if kill_harness and self.__harness.is_launched:
            LOGGER.debug(f"==== Killing Harness for {self.__class__}")
            self.__harness.Kill()
            self.__harness.Wait()

    def Run(self):
        """Launches the component and waits for it to complete."""
        self.assertTrue(self.harness)
        self.harness.Launch()
        self.harness.Wait()

    def GetStdout(self):
        """Returns the contents of the stdout file."""
        self.assertTrue(self.stdout_path)
        return self.GetFileContents(self.stdout_path)

    def GetStderr(self):
        """Returns the contents of the stderr file."""
        self.assertTrue(self.stderr_path)
        return self.GetFileContents(self.stderr_path)

    # Reusable asserts:

    def AssertGoodExitCode(self):
        if self.harness.is_launched:
            LOGGER.debug("Checking that exit code is zero.")
            self.assertEqual(0, self.harness.GetExitCode())

    # Private:

    def __GetEnv(self):
        """Builds the environment variables for running this component.

        Returns:
            dict of str:str
        """
        # By default, we simply use the environment of the test.
        # TODO(matt): We may want a more limited, deterministic, uniform environment.
        env = dict(os.environ)
        env = self.ModifyEnv(env)

        # Look for a test-specific hook.
        method_name = f"ModifyEnv_{self.test_case_name}"
        method = getattr(self, method_name, None)
        if method:
            env = method(env)

        return env


class ComponentTestCase(AbstractComponentTestCase):
    """Concrete manifestation of a test case for testing a single component.

    Used to disambiguate the MRO.
    """


class Component:
    """Information about a single component in a MultiComponentTestCase.

    Properties:
        service_id: Service ID that uniquely identifies this component in a test (str)
        service_conf: Conf object generated for this service.
        xml_conf_path: Path to the XML rendering of the universal conf file (str).
        harness: Harness for the component (harness.ServiceHarness object)

    Additional properties (beginning with a leading underscore) are for internal access by the
    framework only.
    """

    @property
    def service_id(self):
        return self._service.id

    @property
    def service_conf(self):
        return self._service.ServiceConf()

    @property
    def xml_conf_path(self):
        return os.path.join(self._own_dir, f"{self.service_id}.conf")

    @property
    def harness(self):
        return self._harness

    def __init__(self):
        """Initializes a Component object.

        The attributes are populated by MultiComponentTestCase.
        """
        self._service = None  # service_config.Service object
        self._harness_factory = None  # class object of a ServiceHarness subclass
        self._own_dir = None  # str
        self._harness = None  # harness.ProcessHarness object


class SetupConfTestCase(TestCase):
    """Class that finds the configuration file in multiple directories and calls relevant SetupConf.

    Configuration file (default: setup.cmds) is located by checking in several places, starting with
    the test-case-specific data directory, followed by the test-class-specific data directory, the
    test-module-specific data directory, and finally, the test data directory.

    (1) testdata/<test_module_name>/<test_class_name>/<test_case_name>/setup.cmds
    (2) testdata/<test_module_name>/<test_class_name>/setup.cmds
    (3) testdata/<test_module_name>/setup.cmds
    (4) testdata/setup.cmds

    A test has opportunities to modify the configuration.

    (1) The test case can override the SetupConf method by calling SetupConf_test_foo method.

    (2) A method named SetupConf_test_foo, if present, will be invoked during the setup of
        test_foo and presented with the setup_script_path to run with esa-client if setup_script is
        setup.cmds.

    Properties (available after setUp):
        conf_path: Path to the configuration file (str).
        setup_script_path: Path to the configuration file (str).
    """

    @property
    def setup_script_path(self):
        return self.__setup_script_path

    # Optional to override:
    def SetupConf(self, setup_script_path="setup.cmds"):
        return

    def setUp(self, setup_script="setup.cmds"):
        self.__setup_script_path = self.__GetConfPath(setup_script)
        # Allow configuration modifications.
        self.__SetupConf()

    # Private:
    def __GetConfPath(self, setup_script):
        """Locates the setup_script based on the progression documented in this class."""
        dirs = [self.test_case_td_dir, self.test_class_td_dir, self.test_module_td_dir, self.test_td_dir]
        setup_script_paths = [os.path.join(_dir, setup_script) for _dir in dirs]
        for setup_script_path in setup_script_paths:
            if os.path.exists(setup_script_path):
                LOGGER.debug(f"Found setup_script: {setup_script_path}")
                return setup_script_path

        LOGGER.debug(f"Unable to locate {setup_script}, Tried {', '.join(setup_script_paths)}")
        LOGGER.debug(f"Continuing without {setup_script} file.")
        return None

    def __SetupConf(self):
        """Allow the hooks that modify the configuration to run.

        If SetupConf_testname is defined, then only SetupConf_testname will be called,
        else parent SetupConf will be called.
        """
        # Look for a test-specific hook.
        method_name = f"SetupConf_{self.test_case_name}"
        method = getattr(self, method_name, None)
        if method:
            method()
        else:
            self.SetupConf()
