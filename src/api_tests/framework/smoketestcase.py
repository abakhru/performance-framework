import copy
import unittest

import httpx


def get_params(DOMAIN, PATH, EXPECTED_OUTPUT):
    assertion_message = "DON'T FORGET TO SET DOMAIN VARIABLE (url structure: 'http://{domain}{path}')"
    assert DOMAIN is not None, assertion_message

    assertion_message = "DON'T FORGET TO SET THE PATH VARIABLE (url structure: 'http://{domain}{path}')"
    assert PATH is not None, assertion_message

    assertion_message = "DON'T FORGET TO SET THE EXPECTED OUTPUT VARIABLE"
    assert EXPECTED_OUTPUT is not None, assertion_message

    parameters = []
    for domain in DOMAIN:
        for path in PATH:
            for expected_output in EXPECTED_OUTPUT:
                if expected_output.get("data"):
                    expected_output = copy.deepcopy(expected_output)
                    expected_output["data"]["app_name"] = path.split("/")[1]
                parameters.append([domain, path, expected_output])
    return parameters


def create_test(domain, path, expected_output):
    def test(self):
        url = f"http://{domain}{path}"
        output = httpx.get(url).json()
        msg = f"FAILED, url: {url}"
        self.assertEqual(expected_output, output, msg)

    return test


def create_tests(DOMAIN, PATH, EXPECTED_OUTPUT):
    """
    This function takes DOMAIN, PATH, and EXPECTED_OUTPUT arguments and creates
    test functions for every combination of domain and path arguments by calling
    a helper function that returns a test function that makes a request with the url
    'http://{domain}{path}' and compares the result to EXPECTED_OUTPUT. This test function
    is then named 'test_{domain_name}_{app_name}' and set as an attribute of SmokeTestCase
    with the setattr() function which makes it a method of that class and causes it to be ran
    by the unittest framework.
    (note: domain_name is the first item in a list when the domain string is split by '.' and
    app_name is the second item in a list when the path string is split by '/')
    adapted from https://stackoverflow.com/a/2799009
    """
    parameters = get_params(DOMAIN, PATH, EXPECTED_OUTPUT)
    for domain, path, expected_ouput in parameters:
        test = create_test(domain, path, expected_ouput)
        domain_name = domain.split(".")[0]
        name = f"test_{domain_name}_"
        name += path.split("/")[1]
        test.__name__ = name
        setattr(SmokeTestCase, test.__name__, test)


class SmokeTestCase(unittest.TestCase):
    """
    This class is used as a common parent class for tests that involve endpoint checking.
    All that is needed to use this class is to import it and set it as a parent class to
    a TestCase class. After that, the DOMAIN, PATH, and EXPECTED_OUTPUT parameters can be
    specified and passed to the 'create_tests' function (which can be imported from the
    same file as this class) and called within the TestCase class
    """

    pass


if __name__ == "__main__":
    unittest.main()
