class SmsBackend:
    """Interface a real SMS gateway integration must implement."""

    def send(self, phone: str, message: str) -> None:
        raise NotImplementedError
