import os
from functools import lru_cache
import logging
import sqlite3
from time import sleep
from datetime import datetime
import json
from tendo import singleton

from vendus import VendusClient


invoices = sqlite3.connect("invoices.db")


def create_order(invoice):
    return {
        "code": str(invoice["id"]),
        "customerName": invoice["number"] + " " + invoice["amount_gross"],
        "durationMinutes": 10,
        "hideAfterMinutes": 30,
        "expireAfterMinutes": 1,
        "completed": False,
        "accepted": True,
        "startDate": invoice["local_time"].isoformat(),
    }


def write_orders(orders):
    with open("manual_orders.json", "w") as orders_file:
        orders_file.write(json.dumps(orders, indent=4))


me = singleton.SingleInstance()

logging.basicConfig(format="%(asctime)s %(message)s", level=logging.DEBUG)

logging.debug("Starting manual order import")

vendus_api_key = os.getenv("VENDUS_API_KEY")
if not vendus_api_key:
    raise ValueError("Required VENDUS_API_KEY environment variable")

invoicer = VendusClient(vendus_api_key)


@lru_cache
def get_invoice_details(_id):
    return invoicer.get_invoice_details(_id)


while True:

    try:
        cursor = invoices.cursor()
        rows = cursor.execute("select id from invoice where delivery_code is null")
        orders = []

        for (_id,) in rows:
            invoice = get_invoice_details(_id)

            if invoice["type"] == "FR":
                order = create_order(invoice)
                orders.append(order)

        if orders:
            write_orders(orders)

            logging.debug("Exported %d manual invoices", len(orders))

    except Exception:
        logging.exception("Unexpected failure. Will retry")

    sleep(3)
