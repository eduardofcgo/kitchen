import requests
from requests.adapters import HTTPAdapter, Retry


def convert_google_money(units, nanos):
    return round(units + nanos * 10 ** (-9), 2)


class RefreshTokenStrategy:
    def __init__(self, logger, client):
        self.logger = logger
        self.client = client

    def refresh():
        self.logger.debug("Refreshing token")

        self.client.login()


class OtterClient:
    def __init__(self, logger, email, password):
        self.logger = logger
        self.email = email
        self.password = password

        self.login_url = "https://api.tryotter.com/users/sign_in"
        self.orders_url = "https://api.tryotter.com/ufo/otter_order_active"
        self.orders_history_url = "https://api.tryotter.com/ufo/otter_order_history"
        self.graphql_url = "https://api.tryotter.com/graphql"

        self.version = "dd939fbb7062766a7fae374d26620c47b47b6708"

        self.retry_config = Retry(
            total=20,
            backoff_factor=0.2,
            status_forcelist=frozenset({500, 502, 503, 504}),
        )
        self.session = requests.Session()
        self.session.mount(
            "https://api.tryotter.com", HTTPAdapter(max_retries=self.retry_config)
        )
        self.session.headers.update(
            {"application-version": self.version, "accept": "application/json"}
        )

        self.refresh_token_strategy = RefreshTokenStrategy(logger, self)
        self.access_token = None

    def _ensure_logged_in(self):
        if not self.access_token:
            raise ValueError("Not logged in")

    def login(self):
        credentials = {"email": self.email, "password": self.password}

        response = self.session.post(self.login_url, json=credentials)
        response.raise_for_status()

        user_resource = response.json()

        self.access_token = user_resource["accessToken"]
        self.session.headers.update({"authorization": f"Bearer {self.access_token}"})

        self.logger.debug("Logged in")

    def get_orders(self, facility_id, limit=75):
        self._ensure_logged_in()

        params = {"facility_id": facility_id, "limit": limit}

        def request_orders():
            return self.session.get(self.orders_url, params=params)

        response = request_orders()

        if response.status_code == 403:
            self.refresh_token_strategy.refresh()

            response = request_orders()

        response.raise_for_status()

        return response.json()

    def query(self, operation_name, variables, query):
        self._ensure_logged_in()

        data = {"operationName": operation_name, "variables": variables, "query": query}

        response = self.session.post(self.graphql_url, json=data)
        response.raise_for_status()

        return response.json()
