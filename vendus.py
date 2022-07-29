from typing import Tuple
from dataclasses import dataclass, asdict
from datetime import datetime
import base64
import logging
import requests


@dataclass(frozen=True, eq=True)
class InvoiceModifier:
    reference: str
    price: float
    quantity: int
    note: str


@dataclass(frozen=True, eq=True)
class InvoiceItem:
    reference: str
    price: float
    quantity: int
    note: str
    modifiers: Tuple[InvoiceModifier]


@dataclass(frozen=True, eq=True)
class _VendusItem:
    reference: str
    gross_price: str
    qty: int
    text: str


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
        except requests.HTTPError:
            logging.error("Failed to search client %s", response.text)

            raise

        return response.json()

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
        resource_url = self.document_url + str(invoice_id)
        params = {"output": "escpos"}

        response = self.session.get(resource_url, params=params)
        response.raise_for_status()

        invoice_resource = response.json()
        talao = base64.b64decode(invoice_resource["output"])

        return talao

    def get_invoice_details(self, invoice_id):
        resource_url = self.document_url + str(invoice_id)

        response = self.session.get(resource_url)
        try:
            response.raise_for_status()
        except requests.HTTPError:
            logging.error("Failed to obtain invoice details %s", response.text)

            raise

        invoice_resource = response.json()
        self._parse_invoice(invoice_resource)

        return invoice_resource

    def _find_client_by_name(self, name):
        def cannonical_name(client_name):
            return client_name.replace(".", "")

        clients = self.search_client(name=name)

        clients_without_unique_identifiers = [
            client
            for client in clients
            if not client["fiscal_id"] and not client["mobile"]
        ]
        clients_with_same_name = [
            client
            for client in clients_without_unique_identifiers
            if cannonical_name(client["name"]) == cannonical_name(name)
        ]

        return clients_with_same_name

    def guess_client(self, nif, mobile, name):
        if nif:
            clients = self.search_client(nif=nif)
            if clients:
                logging.info("Found existing client for nif %s", nif)
                return clients[0]

            else:
                logging.info("Unable to find client for nif %s", nif)
                return None

        elif mobile:
            clients = self.search_client(external_reference=mobile)
            if len(clients) == 1:
                logging.info("Found existing client for mobile %s", mobile)
                return clients[0]

            if len(clients) > 1:
                raise ValueError("Found more than one client for mobile %s", mobile)

            elif not clients:
                logging.info("Unable to find client for mobile %s", mobile)
                return None

        elif name:
            clients = self._find_client_by_name(name)
            if len(clients) == 1:
                client = clients[0]
                logging.info("Found one client by name %s %s", name, client["id"])
                return client

            if len(clients) > 1:
                client = clients[0]
                logging.info(
                    "Found more than one client by name %s. Will choose first %s",
                    name,
                    client["id"],
                )
                return client

            if not clients:
                logging.info(
                    "Not found any client with name %s",
                    name,
                )
                return None

    def _format_item_note(self, modifers):
        return "\n".join(
            f"{modifier.quantity}x {modifier.reference}" for modifier in modifers
        )

    def _build_item(self, invoice_item):
        price = invoice_item.price
        note = "\n".join(
            filter(
                is_not_empty := bool,
                [self._format_item_note(invoice_item.modifiers), invoice_item.note],
            )
        )

        for modifier in invoice_item.modifiers:
            price += modifier.price * modifier.quantity

        return _VendusItem(
            reference=invoice_item.reference,
            gross_price=str(round(price, 2)),
            qty=invoice_item.quantity,
            text=note if note else None,
        )

    def invoice(
        self,
        invoice_items,
        *,
        config=None,
        client_id=None,
        external_reference=None,
        notes=None,
    ):
        invoice_resource = {
            **(config or {}),
            "items": [asdict(self._build_item(item)) for item in invoice_items],
        }

        if client_id:
            invoice_resource["client"] = {"id": client_id}

        if external_reference:
            invoice_resource["external_reference"] = external_reference

        if notes:
            invoice_resource["notes"] = notes

        response = self.session.post(self.document_url, json=invoice_resource)
        try:
            response.raise_for_status()
        except requests.HTTPError:
            logging.error("Failed to invoice %s", response.text)

            raise

        return response.json()
