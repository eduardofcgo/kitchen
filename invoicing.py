import logging
import sys
import sqlite3
from time import sleep
from datetime import datetime
import dateutil.parser
from collections import Counter
import json
from json.decoder import JSONDecodeError
from tendo import singleton
from dotenv import dotenv_values

from vendus import VendusClient, InvoiceItem, InvoiceModifier
from stack import stack_items
from nif import search as search_nif


def convert_google_money(units, nanos):
    return round(units + nanos * 10 ** (-9), 2)


def generate_invoice_items(ticket, invoice_item_mapping):
    for item in ticket["items"]:
        item_id = item["skuId"]["id"]
        item_details = item["stationItemDetail"]
        item_price = item_details["salePrice"]
        item_quantity = item_details["quantity"]
        item_name = item_details["name"]
        item_note = item_details["note"]

        item_reference = invoice_item_mapping[item_id]
        ignore_item = item_reference is None

        if not ignore_item:
            invoice_modifiers = []

            for modifier in item["itemModifiers"]:
                modifier_id = modifier["skuId"]["id"]
                modifier_details = modifier["orderItemDetail"]
                modifier_price = modifier_details["salePrice"]
                modifier_quantity = modifier_details["quantity"]
                modifier_name = modifier_details["name"]
                modifier_note = modifier_details["note"]

                modifier_reference = invoice_item_mapping[modifier_id]
                ignore_modifier = modifier_reference is None

                if not ignore_modifier:
                    invoice_modifier = InvoiceModifier(
                        reference=modifier_reference,
                        price=convert_google_money(
                            modifier_price["units"], modifier_price["nanos"]
                        ),
                        quantity=modifier_quantity,
                        note=modifier_note,
                    )

                    invoice_modifiers.append(invoice_modifier)

            yield InvoiceItem(
                reference=item_reference,
                price=convert_google_money(item_price["units"], item_price["nanos"]),
                quantity=item_quantity,
                note=item_note,
                modifiers=tuple(invoice_modifiers),
            )


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
        "insert into invoice(id, delivery_code, talao, print_id) values (?, ?, ?, ?)",
        (
            _id,
            code,
            talao_blob,
            None,
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


def invoice_delivery(items, code, platform, nif, name, phone_number, note):
    notes = f"{name} ({platform}) {note}"

    placeholder_address = "Address"

    client = invoicer.guess_client(nif, phone_number, name)
    if not client:
        client = invoicer.create_client(
            nif=nif,
            name=name,
            address=placeholder_address,
            mobile=phone_number,
            external_reference=phone_number,
        )

    invoice = invoicer.invoice(
        items,
        client_id=client["id"],
        config=invoice_config,
        external_reference=code,
        notes=notes,
    )

    return invoice


logging.basicConfig(format="%(asctime)s %(message)s", level=logging.DEBUG)

logging.debug("Starting invoicing")

me = singleton.SingleInstance()

invoices = sqlite3.connect("invoices.db")

config = dotenv_values(".env")
vendus_api_key = config["VENDUS_API_KEY"]

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
        sold_seperatly_references = invoice_mapping["sold_seperatly"]

        tickets = read_json("orders.json")

        for ticket in tickets:
            code = ticket["code"]
            accepted = ticket["accepted"]
            canceled = ticket["canceled"]
            phone_number = ticket["customerPhone"]

            start_time_iso = ticket.get("startDate")

            if not start_time_iso:
                raise ValueError("Expects startDate on order")

            start_time = dateutil.parser.isoparse(start_time_iso).replace(tzinfo=None)

            if accepted and not canceled and not was_delivery_invoiced(code):
                try:
                    name = ticket["customerName"]
                    platform = ticket["platform"]
                    note = ticket["customerNote"]
                    price = ticket["price"]

                    invoice_items = stack_items(
                        generate_invoice_items(ticket, invoice_item_mapping),
                        sold_seperatly_references,
                    )

                    nif = find_nif(ticket)

                    logging.debug("Will invoice %s items %s", code, invoice_items)

                    invoice = invoice_delivery(
                        invoice_items,
                        code,
                        platform,
                        nif,
                        name,
                        phone_number,
                        note,
                    )

                    invoiced_ammount = float(invoice["amount_gross"])

                    if invoiced_ammount != price:
                        sys.exit(
                            f"Invoice ammount {invoiced_ammount} different from ticket price {price}"
                        )

                    invoice_id = invoice["id"]
                    talao = invoicer.get_talao(invoice_id)

                    logging.debug("Invoiced %s - %s", code, invoice_id)

                    try:
                        save_invoice(invoice_id, code, talao)
                    except Exception:
                        logging.exception(
                            "Invoice saved but failed to mark as invoiced"
                        )
                        sys.exit("Exited to prevent invoice duplication")

                    logging.debug("Saved invoice %s - %s", code, invoice_id)
                except KeyError as e:
                    logging.error(
                        "Menu item %s not found on invoicer, please update invoicing.json",
                        e,
                    )
                except (SystemExit, KeyboardInterrupt):
                    raise
                except Exception:
                    logging.exception("Invoicer failed")
    except JSONDecodeError:
        logging.exception("Unable to decode json. Will retry")
    except (SystemExit, KeyboardInterrupt):
        raise
    except Exception:
        logging.exception("Unexpected failure. Will retry")

    sleep(1)
