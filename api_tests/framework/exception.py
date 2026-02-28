"""Exception for A1S automation."""


class Error(Exception):
    """Base class for exceptions raised by this module."""

    pass


class AlreadyLaunchedError(Error):
    """Raised when ProcessHarness.Launch is called twice on the same object."""

    pass


class NotLaunchedError(Error):
    """Raised when certain ProcessHarness methods are called before Launch."""

    pass


class ServerNotReadyError(Error):
    """Raised when A1S app service is not ready."""

    pass


class MissingElementError(Error):
    """Raised when an element is missing."""

    pass


class TcpreplayNotFoundError(Error):
    """Raised when tcpreplay binary is not found."""

    pass


class PcapNotFoundError(Error):
    """Raise when PCAP file is not found"""

    pass


class UnknownAttributeError(Error):
    """Raise when any attributes are unknown"""

    pass


class FileBasedException(Exception):
    """A Base Exception for All File Based Exceptions"""

    def __init__(self, message):
        super().__init__(f"FileBasedException: {message:s}")


class SFTPException(Exception):
    """A Base Exception for All SFTP related Exceptions"""

    def __init__(self, message):
        super().__init__(f"SFTPException: {message}")


class SSHConnectionException(Exception):
    """A Base Exception for All SSHConnection related Exceptions"""

    def __init__(self, message):
        super().__init__(f"SSHConnectionException: {message}")


class TAXIIException(Exception):
    """A Base Exception for All TAXII related Exceptions"""

    def __init__(self, message):
        super().__init__(f"TAXIIException: {message}")
