import logging
import sqlite3
import os
from time import sleep
from datetime import datetime
import dateutil.parser
from collections import Counter
import json
from json.decoder import JSONDecodeError

from vendus import VendusClient, InvoiceItem
from nif import search as search_nif
from tendo import singleton


def generate_invoice_references(ticket, invoice_item_mapping):
    for item in ticket["items"]:
        item_id = item["skuId"]["id"]
        item_details = item["stationItemDetail"]
        item_quantity = item_details["quantity"]
        item_name = item_details["name"]

        invoice_item = invoice_item_mapping[item_id]
        ignore_item = invoice_item is None

        if not ignore_item:
            for _ in range(item_quantity):
                yield invoice_item

        for maybe_modifier in item["itemModifiers"]:

            # TODO: check modifier

            modifier_id = maybe_modifier["skuId"]["id"]
            modifier_details = maybe_modifier["orderItemDetail"]
            modifier_quantity = modifier_details["quantity"]
            modifier_name = modifier_details["name"]

            modifier_invoice_item = invoice_item_mapping[modifier_id]
            ignore_modifier = modifier_invoice_item is None

            if not ignore_modifier:
                for _ in range(modifier_quantity):
                    for _ in range(item_quantity):
                        yield modifier_invoice_item


def create_invoice_items(invoice_references):
    counter = Counter(invoice_references)

    return [
        InvoiceItem(quantity, reference) for (reference, quantity) in counter.items()
    ]


def read_json(file_path):
    with open(file_path) as orders_file:
        return json.load(orders_file)


def find_nif(ticket):
    nifs = search_nif(ticket["customerNote"] or "")

    try:
        return nifs[0]
    except IndexError:
        return None


def was_delivery_invoiced(code):
    cursor = invoices.cursor()

    cursor.execute("select * from invoice where delivery_code = (?)", (code,))

    return cursor.fetchone() is not None


def was_invoice_saved(_id):
    cursor = invoices.cursor()

    cursor.execute("select * from invoice where id = (?)", (_id,))

    return cursor.fetchone() is not None


def save_invoice(_id, code, talao):
    cursor = invoices.cursor()

    talao_blob = sqlite3.Binary(talao)

    cursor.execute(
        "insert into invoice(id, delivery_code, talao, printed) values (?, ?, ?, ?)",
        (
            _id,
            code,
            talao_blob,
            0,
        ),
    )

    invoices.commit()


def import_manual_invoices():
    today_date = datetime.today().date()
    invoices = invoicer.get_invoices()

    for invoice in invoices:
        is_invoiced_today = invoice["date"] == today_date
        is_delivery = "external_reference" in invoice

        if is_invoiced_today and not is_delivery:
            invoice_id = invoice["id"]

            if not was_invoice_saved(invoice_id):
                logging.debug(
                    "Found manual invoice %s %s %s",
                    invoice_id,
                    invoice["amount_gross"],
                    invoice["local_time"].isoformat(),
                )

                talao = invoicer.get_talao(invoice_id)
                save_invoice(invoice_id, None, talao)


def invoice_delivery(items, config, code, platform, nif, name, phone_number):
    notes = f"{name} ({platform})"

    placeholder_address = "Address"

    invoice = invoicer.invoice(
        items,
        config=config,
        external_reference=code,
        nif=nif,
        notes=notes,
        name=name,
        address=placeholder_address,
        mobile=phone_number,
    )

    return invoice


logging.basicConfig(format="%(asctime)s %(message)s", level=logging.DEBUG)

logging.debug("Starting invoicing")

me = singleton.SingleInstance()

invoices = sqlite3.connect("invoices.db")

vendus_api_key = os.getenv("VENDUS_API_KEY")
if not vendus_api_key:
    raise ValueError("Required VENDUS_API_KEY environment variable")

invoice_config = {
    "type": "FR",
    "payments": [{"id": "94305968"}],
    "register_id": 94305980,
}
invoicer = VendusClient(vendus_api_key)

while True:
    try:
        import_manual_invoices()
    except Exception:
        logging.exception("Failed manual import. Will retry")

    try:
        invoice_mapping = read_json("invoicing.json")
        invoice_item_mapping = invoice_mapping["items"]

        tickets = read_json("orders.json")

        for ticket in tickets:
            code = ticket["code"]
            accepted = ticket["accepted"]
            canceled = ticket["canceled"]
            phone_number = ticket["customerPhone"]

            start_date_iso = ticket["startDate"]

            if start_date_iso:
                start_date = dateutil.parser.isoparse(start_date_iso).date()
            else:
                start_date = None

            was_ordered_today = start_date == datetime.today().date()

            if (
                accepted
                and not canceled
                and was_ordered_today
                and not was_delivery_invoiced(code)
            ):
                try:
                    name = ticket["customerName"]
                    platform = ticket["platform"]

                    invoice_references = generate_invoice_references(
                        ticket, invoice_item_mapping
                    )

                    nif = find_nif(ticket)
                    items = create_invoice_items(invoice_references)

                    logging.debug("Will invoice %s items %s", code, items)

                    invoice = invoice_delivery(
                        items,
                        invoice_config,
                        code,
                        platform,
                        nif,
                        name,
                        phone_number,
                    )
                    invoice_id = invoice["id"]
                    talao = invoicer.get_talao(invoice_id)

                    logging.debug("Invoiced %s - %s", code, invoice_id)

                    save_invoice(invoice_id, code, talao)

                    logging.debug("Saved invoice %s - %s", code, invoice_id)

                except KeyError:
                    logging.exception(
                        "Menu item not found on invoicer, please update invoicing.json"
                    )
                except Exception:
                    logging.exception("Invoicer failed. Will retry")

    except JSONDecodeError:
        logging.exception("Unable to decode json. Will retry")
    except Exception:
        logging.exception("Unexpected failure. Will retry")

    sleep(1)
