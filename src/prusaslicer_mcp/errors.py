"""Exception hierarchy. Messages are user-facing and written in Spanish."""


class PrusaMcpError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class SlicerNotFoundError(PrusaMcpError):
    pass


class CliError(PrusaMcpError):
    pass


class CliTimeoutError(CliError):
    pass


class BundleIniError(PrusaMcpError):
    pass


class ProfileNotFoundError(PrusaMcpError):
    pass


class VerificationError(PrusaMcpError):
    def __init__(self, message: str, verification=None):
        super().__init__(message)
        self.verification = verification


class BinaryGcodeError(PrusaMcpError):
    pass


class HostError(PrusaMcpError):
    pass


class ConfirmationError(PrusaMcpError):
    pass


class EngineCapabilityError(PrusaMcpError):
    pass
