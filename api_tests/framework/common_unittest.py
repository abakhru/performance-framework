import filecmp
import gzip
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest

from api_tests.framework.json_util import ParseableJson
from api_tests.framework.logger import LOGGER


class TestCase(unittest.TestCase):
    """
    Properties:
        maxDiff: (inherited) Maximum size (chars) of differences to display in various assert*
                methods.
        maxFileSize: Maximum size of files to diff the "pretty" way in assertFilesEqual and others.
                Files larger than this will be diffed using a "diff" subprocess.
    """

    def setUp(self):
        self.maxDiff = int(1e7)
        self.maxFileSize = int(1e7)

    @staticmethod
    def PythonVersion():
        """Returns:
        Python version string, e.g. '2.4' (str)
        """
        return f"{sys.version_info[0]}.{sys.version_info[1]}"

    @staticmethod
    def GetFileContents(path):
        """Returns the contents of the file.

        Args:
            path: File system path (str)

        Returns:
            Contents of the file (str)
        """
        fd = open(path)
        contents = fd.read()
        fd.close()
        return contents

    @staticmethod
    def GetFileLines(path):
        """Returns the contents of the file as lines of text.

        Args:
            path: File system path (str)

        Returns:
            Contents of the file as lines of text (list of str)
        """
        LOGGER.debug(f"GetFileLines {path}")
        fd = open(path)
        contents = fd.readlines()
        fd.close()
        return contents

    def assertFileExists(self, path, msg=None):
        self.assertTrue(os.path.exists(path), f"File {path} not found ({msg})")

    def assertFilesEqual(self, first, second, msg=None):
        """Asserts that two files have the same contents.

        The exact output in case of a failure varies depending on whether either of the files is
        larger than self.maxFileSize.

        If the files are different and small enough to display 'pretty', they displayed in a
        line-by-line comparison.

        Args:
            first: Path to one file, usually the one containing the expected value (str)
            second: Path to the other file, usually the one containing the actual value (str)
            msg: Message to display if there is a difference (str)
        """
        LOGGER.debug(f"assertFilesEqual {first} {second}")
        self.assertFileExists(first, msg)
        self.assertFileExists(second, msg)

        # See how big the files are to see if we can use the "pretty" diff.
        if os.path.getsize(first) > self.maxFileSize or os.path.getsize(second) > self.maxFileSize:
            LOGGER.debug("Files are too big to diff pretty.")
            diff = self.__DiffFiles(first, second)

            # Indicate if we truncate the output
            if len(diff) >= self.maxDiff:
                there_is_more = "...\n..."
            else:
                there_is_more = ""

            self.assertTrue(
                not diff, f"Unexpected differences between {first} and {second}:\n{diff[: self.maxDiff]}{there_is_more}"
            )
        else:
            LOGGER.debug("Files are small enough to diff pretty.")
            first_contents = self.GetFileLines(first)
            second_contents = self.GetFileLines(second)
            LOGGER.debug(f"Comparing file lines ({len(first_contents)} and {len(second_contents)} lines, respectively)")
            self.assertListEqual(sorted(first_contents), sorted(second_contents), msg)

    def assertFileEqualsKnownGood(self, known_good_file, actual_file, msg=None):
        """Asserts that a file has the same contents as a known-good reference file.

        Args:
            known_good_file: Path to the known good file (str)
            actual_file: Path to the actual file (str)
            msg: Optional message to print in the event of a failure (str)
        """
        self._MaybeUpdateKnownGood(known_good_file, actual_file)
        self.assertFilesEqual(known_good_file, actual_file, msg)

    def assertFilesNotEqual(self, first, second, msg=None):
        """Asserts that two files have different contents.

        Args:
            first: Path to one file, usually the one containing the expected value (str)
            second: Path to the other file, usually the one containing the actual value (str)
            msg: Message to display if there is a difference (str)
        """
        LOGGER.debug(f"assertFilesNotEqual {first} {second}")
        self.assertFileExists(first, msg)
        self.assertFileExists(second, msg)

        diff = self.__DiffFiles(first, second)
        self.assertTrue(diff, f"Expected difference, but files are identical: {first} and {second}")

    def assertDirsEqual(self, first, second, msg=None):
        """Recursively compares two directories.

        Asserts all files exist in both trees, and that uncompressed contents of any gzip'd files
        are equal.
        """
        # list of subdirectories to compare
        dirstack = [""]
        while dirstack:
            _dir = dirstack.pop()
            # paths to compare
            firstdir = os.path.join(first, _dir)
            seconddir = os.path.join(second, _dir)
            dc = filecmp.dircmp(firstdir, seconddir)
            # there must not be unique left or right files, all files must be comparable
            self.assertTrue(not dc.left_only, f"{dc.left_only} not in known good. {msg}")
            self.assertTrue(not dc.right_only, f"Missing {dc.right_only}. {msg}")
            self.assertTrue(not dc.funny_files, f"Failed to compare {dc.funny_files}. {msg}")
            for f in dc.diff_files:
                # We only tolerate diffs between gzip'd files if the uncompressed contents match.
                if os.path.splitext(f)[1] == ".gz":
                    self.assertGZFilesEqual(os.path.join(firstdir, f), os.path.join(seconddir, f), msg)
                elif os.path.splitext(f)[1] == ".tgz":
                    self.assertTarBallsEqual(os.path.join(firstdir, f), os.path.join(seconddir, f), msg)
                else:
                    self.fail(f"{msg or (f'Comparing directories {first} and {second}')}: {f} differs")

            # push any subdirectories and recurse
            for d in dc.common_dirs:
                dirstack.append(os.path.join(_dir, d))

    def assertDirEqualsKnownGood(self, known_good_dir, actual_dir, msg=None):
        """Recursively compares two directories.

        Asserts all files exist in both trees, and that uncompressed contents of any gzip'd files
        are equal.

        Args:
            known_good_dir: Path to the known good directory (str)
            actual_dir: Path to the actual directory (str)
            msg: Optional message to print in the event of a failure (str)
        """
        self._MaybeUpdateKnownGoodDir(known_good_dir, actual_dir)
        self.assertDirsEqual(known_good_dir, actual_dir, msg)

    def __DiffGZFiles(self, first, second):
        """Compares gzip files. Returns true if the files are different."""
        diff = True
        if os.path.exists(first) and os.path.exists(second):
            f1 = gzip.open(first)
            f2 = gzip.open(second)
            c1 = f1.read()
            c2 = f2.read()
            f1.close()
            f2.close()
            diff = c1 != c2
        return diff

    def assertDirsNotEqual(self, first, second, msg=None):
        """Recursively compares two directories.

        Asserts there is some difference between the directories: missing files,
        differences of files, etc.
        """
        # Becomes true when there are differences
        diff = False
        # list of subdirectories to compare
        dirstack = [""]
        while dirstack:
            _dir = dirstack.pop()
            # paths to compare
            firstdir = os.path.join(first, _dir)
            seconddir = os.path.join(second, _dir)
            dc = filecmp.dircmp(firstdir, seconddir)
            # there must not be unique left or right files, all files must be comparable
            if dc.left_only or dc.right_only or dc.funny_files:
                diff = True
                break

            for f in dc.diff_files:
                # We only tolerate diffs between gzip'd files if the uncompressed contents match.
                if os.path.splitext(f)[1] == ".gz":
                    diff = self.__DiffGZFiles(os.path.join(firstdir, f), os.path.join(seconddir, f))
                else:
                    diff = True
                    break

            # push any subdirectories and recurse
            for d in dc.common_dirs:
                dirstack.append(os.path.join(_dir, d))

        self.assertTrue(diff, f"Expected difference, but directories are identical: {first} and {second}. {msg}")

    def assertGZFilesEqual(self, first, second, msg=None):
        """Assert two gzip'd files have equal contents."""
        self.assertTrue(os.path.exists(first), msg)
        self.assertTrue(os.path.exists(second), msg)
        f1 = gzip.open(first)
        f2 = gzip.open(second)
        c1 = f1.read()
        c2 = f2.read()
        f1.close()
        f2.close()
        self.assertEqual(c1, c2, msg)

    def assertGZFileEqualsKnownGood(self, known_good_file, actual_file, msg=None):
        """Assert two gzip'd files have equal contents.

        Args:
            known_good_file: Path to the known good file (str)
            actual_file: Path to the actual file (str)
            msg: Optional message to print in the event of a failure (str)
        """
        self._MaybeUpdateKnownGood(known_good_file, actual_file)
        self.assertGZFilesEqual(known_good_file, actual_file, msg)

    def assertSnapshotsEqual(self, first, second, msg=None):
        """Assert two data snapshots with the same contents.

        Args:
            first: path to the first snapshot (str)
            second: path to the second snapshot (str)
            msg: optional message to print in the event of a failure (str)
        """
        self.assertTarBallsEqual(first, second, msg)

    def assertSnapshotEqualsKnownGood(self, known_good_snapshot, actual_snapshot, msg=None):
        """Assert two data snapshots with the same contents.

        Args:
            known_good_snapshot: Path to the known good snapshot (str)
            actual_snapshot: Path to the actual snapshot (str)
            msg: Optional message to print in the event of a failure (str)
        """
        self.assertTarBallEqualsKnownGood(known_good_snapshot, actual_snapshot, msg)

    def assertTarBallsEqual(self, first, second, msg=None):
        """Compares two tarballs.

        Asserts all files exist in both tarballs, and that contents of any files are equal.
        """
        # check if two tarballs have exactly the same members
        first_tar = tarfile.open(first)
        second_tar = tarfile.open(second)

        self.assertListEqual(sorted(first_tar.getnames()), sorted(second_tar.getnames()), msg)

        # create directories to hold extracted contents for comparison
        first_dir = tempfile.mkdtemp(dir="o")
        second_dir = tempfile.mkdtemp(dir="o")

        try:
            first_tar.extractall(first_dir)
            second_tar.extractall(second_dir)

            # check if these two directories have the same contents
            if msg is None:
                msg = f"Comparing tarballs {first} and {second}"

            self.assertDirsEqual(first_dir, second_dir, msg)

        finally:
            first_tar.close()
            second_tar.close()

            shutil.rmtree(first_dir)
            shutil.rmtree(second_dir)

    def assertTarBallEqualsKnownGood(self, known_good_tarball, actual_tarball, msg=None):
        """Compares two tarballs.

        Asserts all files exist in both tarballs, and that contents of any files are equal.

        Args:
            known_good_tarball: Path to the known good tarball (str)
            actual_tarball: Path to the actual tarball (str)
            msg: Optional message to print in the event of a failure (str)
        """
        self._MaybeUpdateKnownGood(known_good_tarball, actual_tarball)
        self.assertTarBallsEqual(known_good_tarball, actual_tarball, msg)

    def assertLogFilesAlmostEqual(self, first, second, msg=None):
        """Compares two txn log files.

        Ignores any differences in timestamps.

        TODO: Support compressed logs.
        """
        self.assertFileExists(first, msg)
        self.assertFileExists(second, msg)
        first_contents = self.GetFileLines(first)
        second_contents = self.GetFileLines(second)
        first_stripped = self.__StripTxnTimestamps(first_contents, msg or f"Stripping timestamps from {first}")
        second_stripped = self.__StripTxnTimestamps(second_contents, msg or f"Stripping timestamps from {second}")
        self.assertListEqual(first_stripped, second_stripped, msg or f"Comparing log files {first} to {second}")

    def assertLogFileAlmostEqualsKnownGood(self, known_good_file, actual_file, msg=None):
        """Asserts that a txn log file has the same contents as a known-good reference file.

        Ignores any differences in timestamps.

        Args:
            known_good_file: Path to the known good file (str)
            actual_file: Path to the actual file (str)
            msg: Optional message to print in the event of a failure (str)
        """
        self._MaybeUpdateKnownGood(known_good_file, actual_file)
        self.assertLogFilesAlmostEqual(known_good_file, actual_file, msg)

    def _GetStrippedVersionFile(self, inputFile, msg=None):
        """Returns Version-stripped file."""
        self.assertFileExists(inputFile, msg)
        file_contents = self.GetFileLines(inputFile)
        stripped_file = self.__StripConfVersion(file_contents, msg or f"Stripping version# from {inputFile}")
        return stripped_file

    def assertConfFilesAlmostEqual(self, first, second, msg=None):
        """Compares two conf files.

        Ignores any differences in version number.

        """
        first_stripped = self._GetStrippedVersionFile(first)
        second_stripped = self._GetStrippedVersionFile(second)
        self.assertListEqual(first_stripped, second_stripped, msg or f"Comparing Conf files {first} to {second}")

    def assertConfFileAlmostEqualsKnownGood(self, known_good_file, actual_file, msg=None):
        """Asserts that a Conf file has the same contents as a known-good reference file.

        Ignores any differences in version-string change.

        Args:
            known_good_file: Path to the known good file (str)
            actual_file: Path to the actual file (str)
            msg: Optional message to print in the event of a failure (str)
        """
        self.UnsetVersionInConf(actual_file)
        self._MaybeUpdateKnownGood(known_good_file, actual_file)
        self.assertConfFilesAlmostEqual(known_good_file, actual_file, msg)

    def assertAlertFilesAlmostEqual(self, first, second, msg=None):
        """Compares two alert files.

        Ignores any differences in timestamps (lines that start with 'Date = ' or 'Timestamp = ')
        """
        self.assertFileExists(first, msg)
        self.assertFileExists(second, msg)
        first_contents = self.GetFileLines(first)
        second_contents = self.GetFileLines(second)
        first_stripped = self.__StripAlertTimes(first_contents, msg or f"Stripping timestamps from {first}")
        second_stripped = self.__StripAlertTimes(second_contents, msg or f"Stripping timestamps from {second}")
        self.assertListEqual(first_stripped, second_stripped, msg or f"Comparing alert files {first} to {second}")

    def assertAlertFilesAlmostEqualsKnownGood(self, known_good_file, actual_file, msg=None):
        """Asserts that an alert file has the same contents as a known-good reference file.

        Ignores any differences in timestamps.

        Args:
             known_good_file: Path to the known good file (str)
             actual_file: Path to the actual file (str)
             msg: Optional message to print in the event of a failure (str)
        """
        self._MaybeUpdateKnownGood(known_good_file, actual_file)
        self.assertAlertFilesAlmostEqual(known_good_file, actual_file, msg)

    def assertAlertFilesDirAlmostEqual(self, first_alert_dir, second_alert_dir, msg=None):
        """Asserts that two different directories contain the same alerts.

        Args:
            first_alert_dir: path to first alert directory (str)
            second_alert_dir: path to second alert directory (str)
            msg: Optional message to print in the event of a failure (str)
        """
        first_alert_dir_file_path = self.__AlertDir2AlertDirFile(first_alert_dir)
        second_alert_dir_file_path = self.__AlertDir2AlertDirFile(second_alert_dir)
        self.assertAlertFilesAlmostEqual(first_alert_dir_file_path, second_alert_dir_file_path, msg)
        if os.path.isfile(first_alert_dir_file_path) and os.path.exists(first_alert_dir_file_path):
            os.remove(first_alert_dir_file_path)
        if os.path.isfile(second_alert_dir_file_path) and os.path.exists(second_alert_dir_file_path):
            os.remove(second_alert_dir_file_path)

    def assertAlertFilesDirAlmostEqualsKnownGood(self, known_good_alert_dir_file, alert_dir, msg=None):
        """Compares a directory of alerts to a known good representation that directory.

        Ignores any differences in timestamps.
        Method:
            Make a single ordered concatenated file out of the input directory, write a temporary
            file, and compare that against the known good.

        Args:
            known_good_alert_dir_file: path to the known good alert dir file (str)
            alert_dir: Path to the Alert dir (str)
            msg: Optional message to print in the event of a failure (str)
        """
        alert_dir_file_path = self.__AlertDir2AlertDirFile(alert_dir)
        self.assertAlertFilesAlmostEqualsKnownGood(known_good_alert_dir_file, alert_dir_file_path, msg)
        if os.path.isfile(alert_dir_file_path) and os.path.exists(alert_dir_file_path):
            os.remove(alert_dir_file_path)

    def assertSortedFilesEqual(self, first, second, msg=None):
        """Compares two files after line-sorting them.

        This kind of comparison is useful for txn log output when a test produces stable timestamps
        but nondeterministic output sequence (e.g. due to worker thread sharding).

        Args:
            first: File name (str)
            second: file name (str)
            msg: Optional message to print in the event of a failure (str)
        """
        self.assertFileExists(first, msg)
        self.assertFileExists(second, msg)
        first_sorted = sorted(self.GetFileLines(first))
        second_sorted = sorted(self.GetFileLines(second))
        self.assertListEqual(first_sorted, second_sorted, msg or f"Comparing log files {first} to {second}")

    def assertSortedFileEqualsKnownGood(self, known_good_file, actual_file, msg=None):
        """Asserts that a file has the same line-sorted contents as a known-good reference file.

        This kind of comparison is useful for txn log output when a test produces stable timestamps
        but nondeterministic output sequence (e.g. due to worker thread sharding).

        If the ST_UPDATEKNOWNGOOD env var is set to a non-empty value, then the known-good file
        will be overwritten with the contents of the actual file.

        TODO: If the sorted files would be equal, don't update known-good file.

        Args:
            known_good_file: Path to the known good file (str)
            actual_file: Path to the actual file (str)
            msg: Optional message to print in the event of a failure (str)
        """
        self._MaybeUpdateKnownGood(known_good_file, actual_file)
        self.assertSortedFilesEqual(known_good_file, actual_file, msg)

    def assertBalFilesAlmostEqual(self, first, second, msg=None):
        """Compares two bal.json files.

        Ignores any differences in expires and timestamps.
        """
        self.assertFileExists(first, msg)
        self.assertFileExists(second, msg)
        first_contents = self.GetFileLines(first)
        second_contents = self.GetFileLines(second)
        first_stripped = self.__StripBalExpiresAndTimestamps(first_contents)
        second_stripped = self.__StripBalExpiresAndTimestamps(second_contents)
        self.assertListEqual(first_stripped, second_stripped, msg or f"Comparing BAL files {first} to {second}")

    def assertBalFileAlmostEqualsKnownGood(self, known_good_file, actual_file, msg=None):
        """Asserts that a bal.json file has the same contents as a known-good reference file.

        Ignores any differences in timestamps.

        Args:
            known_good_file: Path to the known good file (str)
            actual_file: Path to the actual file (str)
            msg: Optional message to print in the event of a failure (str)
        """
        self._MaybeUpdateKnownGood(known_good_file, actual_file)
        self.assertBalFilesAlmostEqual(known_good_file, actual_file, msg)

    def assertRegexpMatches(self, text, regexp, msg=None):
        """Port from Python 2.7.

        Test that a regexp search matches text. In case of failure, the error message will include
        the pattern and the text (or the pattern and the part of text that unexpectedly
        matched). regexp may be a regular expression object or a string containing a regular
        expression suitable for use by re.search().
        """
        if not re.search(regexp, text):
            self.fail(msg or f'Text {text!r} does not match regular expression "{regexp}"')

    def assertNotRegexpMatches(self, text, regexp, msg=None):
        """Port from Python 2.7.

        Verifies that a regexp search does not match text. Fails with an error message including
        the pattern and the part of text that matches. regexp may be a regular expression object or
        a string containing a regular expression suitable for use by re.search().
        """
        match = re.search(regexp, text)
        if match:
            self.fail(msg or (f'Text {text!r} matches regular expression "{regexp}" at "{match.group(0)}"'))

    def assertExpirationMapFilesAlmostEqual(self, first, second, msg=None):
        """Compares two ExpirationMap files.

        Ignores any differences in timestamps.

        TODO: Support encrypted files.

        Args:
            first: Path to one ExpirationMap file (str)
            second: Path to the other ExpirationMap file (str)
            msg: Optional message to print in the event of a failure (str)
        """
        self.assertFileExists(first, msg)
        self.assertFileExists(second, msg)
        f1 = gzip.open(first)
        f2 = gzip.open(second)
        try:
            try:
                map1 = self.__ParseExpirationMapFile(f1, msg)
                map2 = self.__ParseExpirationMapFile(f2, msg)
            except OSError:
                # If file format is not gzip then an IOException will be thrown while reading.
                # If that happens try getting a normal file handle.
                f1.close()
                f2.close()
                f1 = open(first)
                f2 = open(second)
                map1 = self.__ParseExpirationMapFile(f1, msg)
                map2 = self.__ParseExpirationMapFile(f2, msg)

        finally:
            f1.close()
            f2.close()

        LOGGER.debug("Comparing ExpirationMap files %s and %s:\n%r\n%r", first, second, map1, map2)
        self.assertDictEqual(map1, map2, msg)

    def assertExpirationMapFileAlmostEqualsKnownGood(self, known_good_file, actual_file, msg=None):
        """Compares an ExpirationMap file to a known-good.

        Ignores any differences in timestamps.

        TODO: Support encrypted files.

        Args:
            known_good_file: Path to the known good file (str)
            actual_file: Path to the actual file (str)
            msg: Optional message to print in the event of a failure (str)
        """
        self._MaybeUpdateKnownGood(known_good_file, actual_file)
        self.assertExpirationMapFilesAlmostEqual(known_good_file, actual_file, msg)

    def assertExpirationMapDirsAlmostEqual(self, first_dir, second_dir, msg=None):
        """Compares two directories containing ExpirationMap files.

        Ignores any differences in timestamps.

        TODO: Support encrypted files.

        Args:
            first_dir: Path to one ExpirationMap dir (str)
            second_dir: Path to the other ExpirationMap dir (str)
            msg: Optional message to print in the event of a failure (str)
        """
        dc = filecmp.dircmp(first_dir, second_dir)
        self.assertFalse(dc.left_only, f"{dc.left_only} only on left. {msg}")
        self.assertFalse(dc.right_only, f"{dc.right_only} only on right. {msg}")
        self.assertFalse(dc.funny_files, f"Failed to compare {dc.funny_files}. {msg}")
        for f in dc.diff_files:
            # We only tolerate diffs between files if the contents match using the special
            # ExpirationMap checker.
            self.assertExpirationMapFilesAlmostEqual(os.path.join(first_dir, f), os.path.join(second_dir, f), msg)

    def assertExpirationMapDirAlmostEqualsKnownGood(self, known_good_dir, actual_dir, msg=None):
        """Compares directory containing ExpirationMap files to a known-good directory.

        Ignores any differences in timestamps.

        TODO: Support encrypted files.

        Args:
            known_good_dir: Path to the known good directory (str)
            actual_dir: Path to the actual directory (str)
            msg: Optional message to print in the event of a failure (str)
        """
        self._MaybeUpdateKnownGoodDir(known_good_dir, actual_dir)
        self.assertExpirationMapDirsAlmostEqual(known_good_dir, actual_dir, msg)

    def assertJsonErrorResponse(self, response, msg=None):
        """
        Asserts that a response is a json error response.
        """
        self.assertTrue(self.IsJsonErrorResponse(response), msg)

    def assertNotJsonErrorResponse(self, response, msg=None):
        """
        Asserts that a response is not a JSON error response.
        """
        self.assertFalse(self.IsJsonErrorResponse(response), msg)

    @staticmethod
    def IsJsonErrorResponse(response):
        """
        Checks if a response is a json error response. All json error response in STS system
        has the following format:

            {
                'error': {
                             'message': 'some error',
                             'display': 'some display'
                         }
            }

        Args:
            response: object to check for json error response
        Return:
            True: If response is a json error response
            False: If response is NOT a json error response
        """
        try:
            if (list(response.keys()) == ["error"]) and (
                sorted(response["error"].keys()) == sorted(["display", "message"])
            ):
                return True
            else:
                return False
        except AttributeError:
            return False

    def assertAcceptedCodeWithEmptyResponse(self, response):
        """Verifies an empty HTTP response with Accepted code."""

        self.assertEqual(202, response.code)
        self.assertEqual("Accepted", response.msg)
        self.assertEqual("", response.read())

    def assertNotFoundCodeWithEmptyResponse(self, response):
        """Verifies an empty HTTP response with Not Found code."""

        self.assertEqual(404, response.code)
        self.assertEqual("Not Found", response.msg)
        self.assertEqual("", response.read())

    def assertJSONFileAlmostEqualsKnownGood(self, knowngood_filename, output_filename, ignorefields=None):
        """Assert that two JSON files are equal, except for the content of specified fields.

        If the CTF_UPDATEKNOWNGOOD env var is set to a non-empty value, then the known good
        json file will be overwritten with the contents of the actual json file.

        Args:
            knowngood_filename: The path/file name of the known good JSON file(filename)
            output_filename: The path/file name of the test output JSON file(filename)
            ignorefields: A list of dictionary keys to ignore when comparing.
        """

        if ignorefields is None:
            ignorefields = []
        LOGGER.debug(f"Ignorefields list: {ignorefields}")
        self._MaybeUpdateKnownGood(knowngood_filename, output_filename)

        with open(knowngood_filename, encoding="utf-8") as knowngood_file:
            with open(output_filename, encoding="utf-8") as output_file:
                parsed_knowngood = ParseableJson(json.loads(knowngood_file.read()), ignore_list=ignorefields)
                LOGGER.debug(f"***** PARSED KNOWNGOOD ***** {parsed_knowngood.base_dict}")
                comparison_dict = parsed_knowngood.CompareJson(json.loads(output_file.read()))
                LOGGER.debug(f"***** COMPARISON DICT ***** {comparison_dict}")
        self.assertEqual(parsed_knowngood.base_dict, comparison_dict)

    # Protected:
    def _MaybeUpdateKnownGood(self, known_good_file, actual_file, func_txt_output=None):
        """Creates a known-good file if env var is set.

        If the CTF_UPDATEKNOWNGOOD env var is set to a non-empty value, then the known-good file
        will be overwritten with the contents of the actual file.

        Args:
            known_good_file: Path to the known good file (str)
            actual_file: Path to the actual file (str)
            func_txt_output: Function to print certain files into human-readable format. When
                             passed in, the txt output file will also be overwritten (function)
        """
        if os.environ.get("CTF_UPDATEKNOWNGOOD", None):
            # Create the known-good directory, if necessary.
            known_good_dir = os.path.dirname(known_good_file)
            if known_good_dir and not os.path.exists(known_good_dir):
                os.makedirs(known_good_dir)
            shutil.copyfile(actual_file, known_good_file)

            if func_txt_output:
                func_txt_output(known_good_file, (known_good_file + ".txt"))

    def _MaybeUpdateKnownGoodDir(self, known_good_dir, actual_dir):
        """Creates a known-good directory tree (recursively) if env var is set.

        If the CTF_UPDATEKNOWNGOOD env var is set to a non-empty value, then the known-good dir
        will be overwritten with the contents of the actual dir.

        Args:
            known_good_dir: Path to the known good directory (str)
            actual_dir: Path to the actual dir (str)
        """
        if os.environ.get("CTF_UPDATEKNOWNGOOD", None):
            # Create the parent of the known-good directory, if necessary.
            known_good_parent = os.path.dirname(known_good_dir)
            if known_good_parent and not os.path.exists(known_good_parent):
                os.makedirs(known_good_parent)

            # Completely replace the known-good tree
            if os.path.exists(known_good_dir):
                shutil.rmtree(known_good_dir)
            shutil.copytree(actual_dir, known_good_dir)

    def __DiffFiles(self, first, second):
        """Compares two files using diff subprocess.

        Truncates the diff output to self.maxDiff.

        Args:
            first: Path to first file (str)
            second: Path to second file (str)

        Returns:
            Text describing diffs (str) or empty if no difference
        """
        LOGGER.debug(f"Diffing files {first} and {second}")
        diff = subprocess.Popen(["diff", first, second], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        head = subprocess.Popen(["head", "-c {self.maxDiff}"], stdin=diff.stdout, stdout=subprocess.PIPE)

        diff.stdout.close()
        stdout = head.communicate()[0].decode()
        LOGGER.debug(f"stdout diff: {stdout}")
        diff.wait()
        exit_code = diff.returncode
        # If we got some diffs, that's good enough.  If not, then see if we had a weird exit code
        # from the diff process.
        self.assertTrue(
            stdout or exit_code in [0, 1], msg=f"Problem diffing {first} and {second} ({diff.stderr.read()})"
        )
        if stdout == "":
            return True
        return stdout

    def __list_files_by_mtime(self, alert_dir):
        """_list_files_by_mtime - find each of the files from the alert directory, and sort so that
            the oldest is first.
        Args:
            alert_dir - the path the the alert directory
        Return:
            A list of paths to files in the alert directory, oldest first
        """

        alert_file_list_by_date = []
        for f in os.listdir(alert_dir):
            file_path = os.path.join(alert_dir, f)
            alert_file_list_by_date.append((os.path.getmtime(file_path), file_path))
        alert_file_list_by_date.sort()

        alert_file_list = []
        for alert_time, alert_file_path in alert_file_list_by_date:
            alert_file_list.append(alert_file_path)

        return alert_file_list


# def main():
#    """Entry point which automatically runs all tests in cases defined in the calling module."""
#    privilege.DropPrivileges()
#    unittest2.main()
