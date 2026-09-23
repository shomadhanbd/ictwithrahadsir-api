class SmsBackend:
    """Interface a real SMS gateway integration must implement."""

    def send(self, phone: str, message: str) -> None:
        raise NotImplementedError

    def balance(self) -> dict:
        """Remaining gateway credit, as `{balance, currency}`.

        Defaulted rather than abstract: a backend without a balance API (the
        console one, any future stub) is still a complete backend, and the
        admin readout should show zero rather than 500.
        """
        return {'balance': 0, 'currency': 'BDT'}
