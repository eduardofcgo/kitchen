from dataclasses import dataclass
from datetime import datetime
import base64
import logging
import requests


@dataclass
class InvoiceItem:
    quantity: int
    reference: str


class VendusClient:
    def __init__(self, api_key):
        self.api_key = api_key

        self.session = requests.Session()
        self.session.params.update({"api_key": self.api_key})

        self.duplicated_nif_error_code = "A001"

        self.client_url = "https://www.vendus.pt/ws/v1.1/clients/"
        self.document_url = "https://www.vendus.pt/ws/v1.1/documents/"

    def search_client(self, *, nif=None, name=None, external_reference=None):
        if not any([nif, name, external_reference]):
            raise ValueError("Provide at least one search param")

        search_params = {
            "fiscal_id": nif,
            "name": name,
            "external_reference": external_reference,
        }

        response = self.session.get(self.client_url, params=search_params)

        if response.status_code == 404:
            return []

        try:
            response.raise_for_status()
        except requests.HTTPError as e:
            logging.exception("Failed to search client %s", response.text)

            raise e

        clients_resource = response.json()

        return clients_resource

    def create_client(
        self, *, nif=None, name=None, address=None, mobile=None, external_reference=None
    ):
        if not any([nif, name, address, mobile, external_reference]):
            raise ValueError("Provide at least one value for client")

        client_resource = {}

        if nif:
            client_resource["fiscal_id"] = nif
        if name:
            client_resource["name"] = name
        if address:
            client_resource["address"] = address
        if mobile:
            client_resource["mobile"] = mobile
        if external_reference:
            client_resource["external_reference"] = external_reference

        response = self.session.post(self.client_url, json=client_resource)
        response.raise_for_status()

        created_client = response.json()

        return created_client

    def _parse_date(self, date_str):
        return datetime.strptime(date_str, "%Y-%m-%d").date()

    def _parse_time(self, time_str):
        return datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")

    def _parse_invoice(self, invoice):
        invoice["local_time"] = self._parse_time(invoice["local_time"])
        invoice["date"] = self._parse_date(invoice["date"])

    def get_invoices(self):
        response = self.session.get(self.document_url)
        response.raise_for_status()
        invoices = response.json()

        for invoice in invoices:
            self._parse_invoice(invoice)

        return invoices

    def get_talao(self, invoice_id):
        resource_url = self.document_url + "/" + str(invoice_id)
        params = {"output": "escpos"}

        response = self.session.get(resource_url, params=params)
        response.raise_for_status()

        invoice_resource = response.json()
        talao = base64.b64decode(invoice_resource["output"])

        return talao

    def get_invoice_details(self, invoice_id):
        resource_url = self.document_url + "/" + str(invoice_id)

        response = self.session.get(resource_url)
        try:
            response.raise_for_status()
        except requests.HTTPError as e:
            logging.exception("Failed to obtain invoice details %s", response.text)

            raise e

        invoice_resource = response.json()
        self._parse_invoice(invoice_resource)

        return invoice_resource

    def _guess_client(self, nif, name, address, mobile):
        def cannonical_name(client_name):
            return client_name.replace(".", "")

        if nif:
            clients = self.search_client(nif=nif)
            if clients:
                logging.debug("Found existing client for nif %s", nif)
                return clients[0]
            else:
                client = self.create_client(
                    nif=nif,
                    name=name,
                    address=address,
                    mobile=mobile,
                    external_reference=mobile,
                )

                logging.debug("Created client for nif %s", nif)

                return client

        elif mobile:
            clients = self.search_client(external_reference=mobile)

            if len(clients) == 1:
                logging.debug("Found existing client for mobile %s", mobile)
                return clients[0]

            if len(clients) > 1:
                raise ValueError("Found more than one client for mobile %s", mobile)

            elif not clients:
                client = self.create_client(
                    nif=nif,
                    name=name,
                    address=address,
                    mobile=mobile,
                    external_reference=mobile,
                )
                logging.debug(
                    "Created new client for mobile %s with %s %s", mobile, name, address
                )

                return client

        elif name:
            clients = self.search_client(name=name)
            possible_matches = [
                client
                for client in clients
                if not client["fiscal_id"]
                and not client["mobile"]
                and cannonical_name(client["name"]) == cannonical_name(name)
            ]

            if len(possible_matches) == 1:
                client = possible_matches[0]
                logging.debug("Found one match by name %s %s", name, client["id"])

                return client

            if len(possible_matches) > 1:
                client = possible_matches[0]
                logging.debug(
                    "Found more than one match by name %s. Will choose first %s",
                    name,
                    client["id"],
                )

                return client

            if not possible_matches:
                logging.debug(
                    "Not found any matches by name. Will create client %s %s",
                    name,
                    address,
                )
                return self.create_client(name=name, address=address)

    def _build_invoice_items(self, items):
        return [{"qty": item.quantity, "reference": item.reference} for item in items]

    def invoice(
        self,
        items,
        *,
        config=None,
        nif=None,
        external_reference=None,
        notes=None,
        name=None,
        address=None,
        mobile=None,
    ):
        invoice_resource = {
            **(config or {}),
            "items": self._build_invoice_items(items),
        }

        client = self._guess_client(nif, name, address, mobile)

        if not client:
            raise ValueError("Client not found, unable to invoice")

        invoice_resource["client"] = {"id": client["id"]}

        if external_reference:
            invoice_resource["external_reference"] = external_reference

        if notes:
            invoice_resource["notes"] = notes

        response = self.session.post(self.document_url, json=invoice_resource)
        try:
            response.raise_for_status()
        except requests.HTTPError as e:
            logging.exception("Failed to invoice %s", response.text)

            raise e

        return response.json()
